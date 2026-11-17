"""Build a static reference from RDF only; never read private input directories."""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import zipfile
from pathlib import Path
from urllib.parse import quote
from xml.etree import ElementTree as ET

from rdflib import BNode, Graph, Literal, Namespace, URIRef
from rdflib.compare import to_canonical_graph
from rdflib.namespace import DCTERMS, RDF, RDFS, SH, XSD

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "target/site"
ADMS = Namespace("http://www.w3.org/ns/adms#")
REPO = "https://github.com/Deutsche-Digitale-Bibliothek/ddb-metadata-model"
PROFILES = ("items", "records", "datasets", "catalog")
ESC = html.escape


def write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def local_name(node):
    return str(node).rsplit("/", 1)[-1].rsplit("#", 1)[-1]


def anchor(node):
    return "term-" + hashlib.sha256(str(node).encode()).hexdigest()[:16]


def qname(g, node):
    if isinstance(node, URIRef):
        try:
            return g.namespace_manager.normalizeUri(node)
        except ValueError:
            return str(node)
    return str(node)


def values(g, subject, predicate):
    return sorted(g.objects(subject, predicate), key=lambda x: (getattr(x, "language", "") != "de", str(x), x.n3()))


def text(g, subject, predicate, fallback=""):
    candidates = values(g, subject, predicate)
    return str(candidates[0]) if candidates else fallback


def labels(g, subject, predicate):
    return "<br>".join(ESC(str(v)) + (f' <small lang="en">@{ESC(v.language)}</small>' if v.language else "") for v in values(g, subject, predicate))


def render(g, node, depth=0):
    if isinstance(node, Literal):
        return '<span class="literal">' + ESC(node.n3()) + '</span>'
    if isinstance(node, URIRef):
        return f'<a href="{ESC(str(node), quote=True)}"><code>{ESC(qname(g, node))}</code></a>'
    if depth > 8:
        raise ValueError("Recursive RDF structure exceeds rendering depth")
    if (node, RDF.first, None) in g:
        return "( " + " · ".join(render(g, x, depth + 1) for x in g.items(node)) + " )"
    return "[ " + "; ".join(f'{ESC(qname(g, p))}: {render(g, o, depth + 1)}' for p, o in sorted(g.predicate_objects(node), key=lambda x: (str(x[0]), x[1].n3()))) + " ]"


def page(title, body, level=0):
    prefix = "../" * level
    nav = ''.join(f'<a href="{prefix}{p}/index.html">{p.title()}</a>' for p in PROFILES)
    return f'''<!doctype html><html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{ESC(title)} · DDB Metadata Model</title><link rel="stylesheet" href="{prefix}assets/style.css"></head><body><header><a class="brand" href="{prefix}index.html">DDB <span>Metadata Model</span></a><nav aria-label="Bereiche">{nav}<a href="{prefix}reports/index.html">Berichte</a><a href="{prefix}versions.html">Versionen</a></nav></header><main>{body}</main><footer>Aus RDF erzeugt · Apache-2.0 · <a href="{REPO}">Quellen auf GitHub</a></footer></body></html>'''


def canonical_serializations(g):
    c = to_canonical_graph(g)
    ttl = "\n".join(sorted(" ".join((s.n3(), p.n3(), o.n3())) + " ." for s, p, o in c)) + "\n"
    # Expanded JSON-LD is a model serialization, deliberately not a payload context.
    def ordered(value, preserve_order=False):
        if isinstance(value, list):
            result = [ordered(v) for v in value]
            return result if preserve_order else sorted(result, key=lambda v: json.dumps(v, sort_keys=True, ensure_ascii=False))
        if isinstance(value, dict):
            return {k: ordered(v, k == "@list") for k, v in sorted(value.items())}
        return value
    jsonld = json.dumps(ordered(json.loads(c.serialize(format="json-ld"))), ensure_ascii=False, indent=2) + "\n"
    # Sort RDF/XML elements as well as attributes, preserving canonical blank node IDs.
    xml = ET.fromstring(c.serialize(format="xml"))
    # RDFLib's pretty-printer attaches indentation to whichever element was last.
    # Remove only structural whitespace before sorting; literal text is untouched.
    for element in xml.iter():
        element.tail = None
        if len(element) and element.text is not None and not element.text.strip():
            element.text = None
    for description in xml:
        description[:] = sorted(description, key=lambda e: (e.tag, sorted(e.attrib.items()), e.text or ""))
    xml[:] = sorted(xml, key=lambda e: sorted(e.attrib.items()))
    ET.indent(xml, space="  ")
    rdfxml = ET.canonicalize(ET.tostring(xml, encoding="unicode")) + "\n"
    return {"ttl": ttl, "jsonld": jsonld, "rdf": rdfxml}


def svg(g, edges, title):
    width, row = 1160, 88
    height = max(130, len(edges) * row + 64)
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="title" viewBox="0 0 {width} {height}"><title id="title">{ESC(title)}</title><defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="#236d7e"/></marker></defs><rect width="100%" height="100%" fill="#f4f7f7"/>']
    if not edges:
        parts.append('<text x="32" y="64" font-family="sans-serif" font-size="17">Keine entsprechenden Beziehungen im RDF modelliert.</text>')
    for i, (source, relation, target) in enumerate(edges):
        y = 28 + i * row
        parts.append(f'<rect x="20" y="{y}" width="350" height="50" rx="6" fill="white" stroke="#90b9c2"/><rect x="790" y="{y}" width="350" height="50" rx="6" fill="white" stroke="#90b9c2"/><path d="M 371 {y+25} H 778" stroke="#236d7e" marker-end="url(#arrow)"/><text x="580" y="{y+13}" text-anchor="middle" font-family="monospace" font-size="13">{ESC(relation)}</text>')
        for x, label in ((195, source), (965, target)):
            parts.append(f'<text x="{x}" y="{y+31}" text-anchor="middle" font-family="monospace" font-size="14">{ESC(label)}</text>')
    return "".join(parts) + '</svg>'


def terms_section(g, terms, kind):
    chunks = [f'<section id="{kind}"><h2>{"Klassen" if kind == "classes" else "Properties"} <span class="count">{len(terms)}</span></h2>']
    for subject in terms:
        chunks.append(f'<article id="{anchor(subject)}"><h3>{ESC(text(g, subject, RDFS.label, local_name(subject)))}</h3><p>{render(g, subject)}</p>')
        annotations = labels(g, subject, RDFS.label)
        if annotations:
            chunks.append(f'<p>{annotations}</p>')
        comments = labels(g, subject, RDFS.comment)
        chunks.append(f'<p>{comments or "<em>Keine Erläuterung in der RDF-Quelle hinterlegt.</em>"}</p>')
        others = [(p, o) for p, o in g.predicate_objects(subject) if p not in (RDFS.label, RDFS.comment)]
        chunks.append('<dl>' + ''.join(f'<dt>{ESC(qname(g, p))}</dt><dd>{render(g, o)}</dd>' for p, o in sorted(others, key=lambda v: (str(v[0]), str(v[1])))) + '</dl></article>')
    return ''.join(chunks) + '</section>'


def rules_section(g, shapes):
    result = ['<section id="rules"><h2>Modellierte Regeln</h2><p>Fachlicher Arbeitsentwurf. Die API aktiviert diese Shapes nicht. Alle Parameter unten stammen aus dem Regelgraphen; fehlende Constraints bedeuten keine zusätzliche Anforderung.</p>']
    documentary = {SH.name, SH.description, SH.order, SH.group, RDFS.label, RDFS.comment, RDF.type}
    for shape in shapes:
        result.append(f'<article id="shape-{ESC(local_name(shape))}"><h3>{ESC(text(g, shape, SH.name, local_name(shape)))}</h3><p>{render(g, shape)}</p><p>{labels(g, shape, SH.description)}</p><dl>')
        for p, o in sorted(g.predicate_objects(shape), key=lambda pair: (str(pair[0]), str(pair[1]))):
            if p in documentary or p == SH.property:
                continue
            result.append(f'<dt>{ESC(qname(g, p))}</dt><dd>{render(g, o)}</dd>')
        result.append('</dl>')
        properties = sorted(g.objects(shape, SH.property), key=lambda s: (float(text(g, s, SH.order, "0")), str(g.value(s, SH.path))))
        for prop in properties:
            result.append(f'<h4>{ESC(text(g, prop, SH.name, qname(g, g.value(prop, SH.path))))}</h4><p>{labels(g, prop, SH.description)}</p><dl>')
            for p, o in sorted(g.predicate_objects(prop), key=lambda pair: (str(pair[0]), str(pair[1]))):
                if p not in documentary:
                    result.append(f'<dt>{ESC(qname(g, p))}</dt><dd>{render(g, o)}</dd>')
            result.append('</dl>')
        result.append('</article>')
    return ''.join(result) + '</section>'


def build_profile(profile, commit, ref, dirty):
    metadata_file = ROOT / "profiles" / f"{profile}.ttl"
    metadata = Graph().parse(metadata_file, format="turtle")
    subject = next(metadata.subjects(DCTERMS.identifier, Literal(profile)))
    version = text(metadata, subject, DCTERMS.hasVersion)
    status = text(metadata, subject, ADMS.status)
    sources = [f"{profile}_{part}.ttl" for part in ("class_definitions", "property_definitions", "shapes")]
    declared = {str(u).rsplit("/", 1)[-1] for u in metadata.objects(subject, DCTERMS.hasPart)}
    if set(sources) != declared:
        raise ValueError(f"{profile}: profile/source manifest mismatch")
    graph = Graph()
    for source in sources:
        graph.parse(ROOT / source, format="turtle")
    vocab = Graph()
    for source in sources[:2]:
        vocab.parse(ROOT / source, format="turtle")
    classes = sorted(set(vocab.subjects(RDF.type, RDFS.Class)), key=str)
    properties = sorted(set(vocab.subjects(RDF.type, RDF.Property)), key=str)
    shapes = sorted(set(graph.subjects(RDF.type, SH.NodeShape)), key=lambda s: (float(text(graph, s, SH.order, "0")), str(s)))
    destination = OUT / profile
    downloads = destination / "downloads"
    downloads.mkdir(parents=True, exist_ok=True)
    for source in sources:
        shutil.copyfile(ROOT / source, downloads / source)
    shutil.copyfile(metadata_file, downloads / f"{profile}_profile.ttl")
    bundle = graph + metadata
    for extension, content in canonical_serializations(bundle).items():
        write(downloads / f"{profile}.{extension}", content)
    for extension, rdf_format in (("ttl", "turtle"), ("jsonld", "json-ld"), ("rdf", "xml")):
        reparsed = Graph().parse(downloads / f"{profile}.{extension}", format=rdf_format)
        if to_canonical_graph(reparsed) != to_canonical_graph(bundle):
            # Graph equality compares identifiers, use canonical triple sets instead.
            if set(to_canonical_graph(reparsed)) != set(to_canonical_graph(bundle)):
                raise ValueError(f"{profile}: {extension} graph roundtrip differs")
    vocabulary_edges = [(qname(graph, s), qname(graph, p), qname(graph, o)) for p in (RDFS.subClassOf, RDFS.subPropertyOf, RDFS.domain, RDFS.range) for s, o in vocab.subject_objects(p)]
    rule_edges = []
    for shape in shapes:
        for target in graph.objects(shape, SH.targetClass):
            for prop in graph.objects(shape, SH.property):
                path = qname(graph, graph.value(prop, SH.path))
                kind = graph.value(prop, SH.nodeKind)
                end = qname(graph, kind) if kind else "RDF-Wert (ohne Typvorgabe)"
                rule_edges.append((qname(graph, target), path, end))
    write(destination / "vocabulary.svg", svg(graph, sorted(vocabulary_edges), f"{profile.title()}: explizite Vokabularbeziehungen"))
    write(destination / "rules.svg", svg(graph, sorted(rule_edges), f"{profile.title()}: SHACL-Zielklassen, Pfade und Werteknotenarten"))
    source_sha = {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in [metadata_file, *(ROOT / s for s in sources)]}
    manifest = {"profile": profile, "version": version, "status": status, "sourceCommit": commit, "ref": ref, "dirty": dirty, "sources": source_sha, "classes": len(classes), "properties": len(properties), "nodeShapes": len(shapes), "triples": len(bundle)}
    write(downloads / "manifest.json", json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
    body = f'<p class="eyebrow">ANWENDUNGSPROFIL / {ESC(status)}</p><h1>{ESC(text(metadata, subject, DCTERMS.title))}</h1><p class="intro">{ESC(text(metadata, subject, DCTERMS.description))}</p><div class="meta">Version {ESC(version)} · {ESC(status)} · Commit <code>{ESC(commit)}</code>{" · lokale Änderungen" if dirty else ""}</div>'
    publisher = metadata.value(subject, DCTERMS.publisher)
    body += f'<p>Herausgeber: {ESC(text(metadata, publisher, RDFS.label, str(publisher)))} · <a href="{ESC(str(metadata.value(subject, DCTERMS.license)))}">Lizenz</a></p><nav class="toc" aria-label="Profilinhalt"><a href="#classes">{len(classes)} Klassen</a><a href="#properties">{len(properties)} Properties</a><a href="#rules">{len(shapes)} Shapes</a><a href="#diagrams">Diagramme</a><a href="#downloads">Downloads</a></nav>'
    if profile in ("items", "records"):
        shutil.copyfile(ROOT / f"{profile}.ttl", downloads / f"{profile}-api-policy.ttl")
        body += f'<aside><strong>Aktive API-Policy:</strong> <a href="downloads/{profile}-api-policy.ttl">{profile}.ttl</a> prüft ausschließlich, ob der RDF-Graph mindestens ein Triple enthält. Fester Target-Knoten + SHACL-SPARQL erreichen auch den leeren Graphen. Die nachfolgenden fachlichen Regeln werden von der API nicht geladen.</aside>'
    body += terms_section(vocab, classes, "classes") + terms_section(vocab, properties, "properties") + rules_section(graph, shapes)
    body += '<section id="diagrams"><h2>Diagramme</h2><p>Gezeigt werden ausschließlich RDF-Aussagen. Unterklassen von ddbv:-Hilfsklassen bilden lokale Profilgruppen. Es gibt keine Domain-/Range-Zuordnung aller Properties. Die Regelsicht zeigt Zielklasse → Pfad → zulässige Knotenart, keine behauptete Zielklasse der Beziehung.</p><h3>Vokabular</h3><a href="vocabulary.svg">SVG herunterladen</a><img class="diagram" src="vocabulary.svg" alt="Explizite Unterklassenbeziehungen"><h3>Regelsicht</h3><a href="rules.svg">SVG herunterladen</a><img class="diagram" src="rules.svg" alt="SHACL-Zielklassen, Pfade und Knotenarten"></section>'
    links = ''.join(f'<li><a href="downloads/{quote(p.name)}">{ESC(p.name)}</a></li>' for p in sorted(downloads.iterdir()) if p.is_file())
    body += f'<section id="downloads"><h2>Downloads</h2><p>Das Bündel enthält Klassen, Properties, Entwurfs-Shapes und Profilmetadaten. JSON-LD serialisiert das Profilmodell; es ist kein JSON-LD-Context für Nutzdaten und kein Ersatz für die Validierung.</p><ul>{links}</ul></section>'
    write(destination / "index.html", page(text(metadata, subject, DCTERMS.title), body, 1))
    return manifest


def deterministic_zip(path, source):
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for file in sorted(source.rglob("*")):
            if file.is_file():
                info = zipfile.ZipInfo(file.relative_to(source).as_posix(), (1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o644 << 16
                archive.writestr(info, file.read_bytes())


def build(args):
    if OUT.exists():
        shutil.rmtree(OUT)  # Constant path inside this repository; private inputs are never traversed.
    OUT.mkdir(parents=True)
    commit = os.environ.get("SOURCE_COMMIT") or git("rev-parse", "HEAD")
    ref = args.ref or os.environ.get("GITHUB_REF_NAME", "local")
    dirty = bool(git("status", "--porcelain", "--untracked-files=normal"))
    manifests = [build_profile(p, commit, ref, dirty) for p in PROFILES]
    write(OUT / "assets/style.css", (ROOT / "scripts/style.css").read_text(encoding="utf-8"))
    report_source = ROOT / "target/reports"
    if report_source.is_dir():
        # Only the public synthetic-test report directory is copied.
        shutil.copytree(report_source, OUT / "reports")
        for report_file in (OUT / "reports").glob("*.ttl"):
            report_graph = Graph().parse(report_file, format="turtle")
            # Jena's blank-node identifiers are process-local. Canonicalize the
            # published serialization, including embedded anonymous source shapes.
            canonical = to_canonical_graph(report_graph)
            write(report_file, "\n".join(sorted(" ".join((s.n3(), p.n3(), o.n3())) + " ." for s, p, o in canonical)) + "\n")
    else:
        write(OUT / "reports/index.html", page("Berichte", '<h1>Berichte</h1><p>Noch keine Jena-Ergebnisse vorhanden. Zuerst <code>mvn verify</code> ausführen.</p>', 1))
    test_files = sorted((ROOT / "target/surefire-reports").glob("TEST-*.xml"))
    test_totals = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    for path in test_files:
        suite = ET.parse(path).getroot()
        for key in test_totals:
            test_totals[key] += int(suite.attrib.get(key, "0"))
    verified = bool(test_files) and not (test_totals["failures"] or test_totals["errors"])
    status = "Tests erfolgreich" if verified else ("Tests fehlgeschlagen" if test_files else "Tests noch nicht ausgeführt")
    cards = ''.join(f'<a class="card" href="{m["profile"]}/index.html"><span class="eyebrow">{m["status"]} / {m["version"]}</span><h2>{m["profile"].title()} <span aria-hidden="true">↗</span></h2><p>{m["classes"]} Klassen · {m["properties"]} Properties · {m["nodeShapes"]} Shapes</p></a>' for m in manifests)
    body = f'<p class="eyebrow">DEUTSCHE DIGITALE BIBLIOTHEK / MODELLWERKSTATT</p><h1>Ein Modell.<br>Vier Perspektiven.</h1><p class="intro">RDF-Vokabular, ausführbare Regeln und ihre Grenzen. Aus denselben Turtle-Quellen erzeugt; fachlicher Arbeitsentwurf.</p><div class="cards">{cards}</div><section><h2>Was wird geprüft?</h2><p>Die API lädt ausschließlich <code>items.ttl</code> und <code>records.ttl</code>: mindestens ein Triple. Die fachlichen <code>*_shapes.ttl</code> bleiben separate Entwürfe. Ein grüner Testlauf bestätigt die erwarteten Testergebnisse, keine vollständige fachliche Konformität.</p><p><a class="button" href="reports/index.html">{status} →</a> {test_totals["tests"]} Tests · {test_totals["failures"]} Fehlschläge · {test_totals["errors"]} Fehler</p><p>Apache Jena 6.2.0 · keine zusätzliche Inferenz · keine automatischen Imports · Warnungen können <code>sh:conforms false</code> auslösen.</p></section><section><h2>Quellen → Sichten</h2><p>Klassen und Properties bleiben RDFS/RDF. Die Referenz zeigt alle definierten Begriffe einschließlich vorhandener Sprachfassungen. Diagramme zeigen ausschließlich explizite Beziehungen. Downloads enthalten Turtle, JSON-LD und RDF/XML.</p><p><a href="versions.html">Versionen und Downloads</a> · <a href="{REPO}/blob/main/README.md">Pflege und lokale Ausführung</a></p></section>'
    write(OUT / "index.html", page("Übersicht", body))
    write(OUT / "versions.html", page("Versionen", f'<p class="eyebrow">VERSIONEN / REPRODUZIERBARKEIT</p><h1>Welcher Stand?</h1><p>Ref <code>{ESC(ref)}</code> · Quellcommit <code>{ESC(commit)}</code>{" · lokale Änderungen" if dirty else ""}.</p><p>Die Startseite auf Pages zeigt den zuletzt erfolgreich geprüften main-Stand. Jeder Release enthält seine eigene statische Dokumentation als ZIP und Downloads mit Quellcommit und SHA-256-Prüfsummen. Frühere Releases werden nicht überschrieben.</p><p><a href="{REPO}/releases">Versionierte Dokumentation und Downloads auf GitHub Releases →</a></p><p><a href="downloads/model.zip">Alle öffentlichen Modellquellen und Serialisierungen</a> · <a href="downloads/manifest.json">Build-Manifest</a> · <a href="downloads/SHA256SUMS">Prüfsummen</a></p>'))
    download_root = OUT / "downloads"
    download_root.mkdir()
    public_sources = ROOT / "target/public-model"
    if public_sources.exists():
        shutil.rmtree(public_sources)
    public_sources.mkdir()
    for profile in PROFILES:
        shutil.copytree(OUT / profile / "downloads", public_sources / profile)
    shutil.copyfile(ROOT / "LICENSE", public_sources / "LICENSE")
    deterministic_zip(download_root / "model.zip", public_sources)
    manifest = {"sourceCommit": commit, "ref": ref, "dirty": dirty, "profiles": manifests, "jena": "6.2.0", "rdflib": "7.6.0", "testResults": test_totals}
    write(download_root / "manifest.json", json.dumps(manifest, sort_keys=True, ensure_ascii=False, indent=2) + "\n")
    files = [p for p in OUT.rglob("*") if p.is_file() and p.suffix in (".ttl", ".jsonld", ".rdf", ".zip", ".json", ".svg")]
    write(download_root / "SHA256SUMS", ''.join(f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(OUT).as_posix()}\n' for p in sorted(files)))
    write(OUT / ".nojekyll", "")
    print(json.dumps({"output": str(OUT), "profiles": manifests, "tests": test_totals}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ref", help="Visible release tag/ref (commit stays resolved from Git)")
    build(parser.parse_args())
