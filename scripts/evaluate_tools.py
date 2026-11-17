"""Reproduce the Items tool trial without changing model semantics or source files."""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import re
import subprocess
import sys

from rdflib import Graph, Namespace, RDF, RDFS

ROOT = Path(__file__).resolve().parents[1]
SH = Namespace("http://www.w3.org/ns/shacl#")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--java", default="java")
    parser.add_argument("--shacl-play-jar", type=Path, default=ROOT / "target/tools/shacl-play-app-0.12.6-onejar.jar")
    parser.add_argument("--report", type=Path, help="A public Jena Items RDF validation report from mvn verify")
    args = parser.parse_args()
    jar = args.shacl_play_jar.resolve()
    if not jar.is_file():
        parser.error(f"Missing SHACL Play 0.12.6 CLI jar: {jar}")
    jar_sha256 = hashlib.sha256(jar.read_bytes()).hexdigest()
    if jar_sha256 != "cfc3794b116929a938873ec025c09281b77373ee509ed233542c6fe72feb6e44":
        parser.error("SHACL Play jar checksum does not match the evaluated 0.12.6 release")
    if importlib.metadata.version("pylode") != "3.2.1":
        parser.error("Tool trial requires pylode==3.2.1")

    out = ROOT / "target/tool-evaluation"
    out.mkdir(parents=True, exist_ok=True)
    for name in ("pylode-items.html", "shacl-play-items.html", "shacl-play-items.iuml", "shacl-play-items.svg", "shacl-play-report.html"):
        (out / name).unlink(missing_ok=True)
    graph = Graph()
    for name in ("items_class_definitions.ttl", "items_property_definitions.ttl", "items_shapes.ttl", "profiles/items.ttl"):
        graph.parse(ROOT / name, format="turtle")
    bundle = out / "items.ttl"
    graph.serialize(bundle, format="turtle")
    summary = {
        "versions": {"pylode": "3.2.1", "shaclPlay": "0.12.6", "rdflib": importlib.metadata.version("rdflib")},
        "shaclPlayJarSha256": jar_sha256,
        "expected": {
            "classes": len(set(graph.subjects(RDF.type, RDFS.Class))),
            "properties": len(set(graph.subjects(RDF.type, RDF.Property))),
            "nodeShapes": len(set(graph.subjects(RDF.type, SH.NodeShape))),
        },
        "commands": {},
    }

    def run(name: str, command: list[str]) -> None:
        with (out / f"{name}.log").open("w", encoding="utf-8") as log:
            try:
                result = subprocess.run(command, cwd=out, stdout=log, stderr=subprocess.STDOUT, timeout=180)
                code: int | str = result.returncode
            except subprocess.TimeoutExpired:
                code = "timeout"
        summary["commands"][name] = {"command": command, "exitCode": code}

    run("pylode", [sys.executable, "-m", "pylode.cli", str(bundle), "-o", "pylode-items.html"])
    prefix = [args.java, "-jar", str(jar)]
    run("shacl-play-doc", prefix + ["doc", "-i", str(bundle), "-l", "de", "-nsd", "-o", "shacl-play-items.html"])
    run("shacl-play-draw", prefix + ["draw", "-i", str(bundle), "-s", "-o", "shacl-play-items.iuml", "-o", "shacl-play-items.svg"])
    if args.report:
        report = args.report.resolve()
        if not report.is_file():
            parser.error(f"Missing report: {report}")
        run("shacl-play-report", prefix + ["report", "-i", str(report), "-s", str(bundle), "-o", "shacl-play-report.html"])

    def read(name: str) -> str:
        path = out / name
        return path.read_text(encoding="utf-8") if path.is_file() else ""

    pylode = read("pylode-items.html")
    shape_doc = read("shacl-play-items.html")
    diagram = read("shacl-play-items.svg")
    summary["pylode"] = {
        "classEntries": len(re.findall(r'class="class entity"', pylode)),
        "propertyEntries": len(re.findall(r'class="property entity"', pylode)),
        "concatenatedLanguageLabels": "HerstellungsortPlace of manufacture" in pylode,
    }
    summary["shaclPlay"] = {
        "documentedNodeShapes": sum(str(node) + "</code>" in shape_doc for node in graph.subjects(RDF.type, SH.NodeShape)),
        "blankDocumentTitle": "<title>&nbsp;</title>" in shape_doc,
        "svgContainsSyntaxError": "Syntax Error" in diagram,
        "reportHtmlGenerated": bool(read("shacl-play-report.html")) if args.report else None,
    }
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"expected": summary["expected"], "pylode": summary["pylode"], "shaclPlay": summary["shaclPlay"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
