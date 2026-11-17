"""Fail on missing local links, vocabulary terms, broken diagrams or private exports."""
import hashlib
import json
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit
from xml.etree import ElementTree as ET

from rdflib import Graph
from rdflib.namespace import RDF, RDFS

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "target/site"


class Document(HTMLParser):
    def __init__(self, content):
        super().__init__(convert_charrefs=True)
        self.links = []
        self.ids = set()
        self.feed(content)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if "id" in attrs:
            assert attrs["id"] not in self.ids, f"Duplicate anchor {attrs['id']}"
            self.ids.add(attrs["id"])
        for key in ("href", "src"):
            if key in attrs:
                self.links.append(attrs[key])


def main():
    documents = {p.resolve(): Document(p.read_text(encoding="utf-8")) for p in SITE.rglob("*.html")}
    checked = 0
    for path, document in documents.items():
        for link in document.links:
            url = urlsplit(link)
            if url.scheme or url.netloc:
                continue
            target = (path.parent / unquote(url.path)).resolve() if url.path else path
            if target.is_dir():
                target /= "index.html"
            assert target.is_relative_to(SITE.resolve()), f"Link leaves site: {path}: {link}"
            assert target.exists(), f"Broken link: {path}: {link}"
            if url.fragment and target in documents:
                assert unquote(url.fragment) in documents[target].ids, f"Missing fragment: {path}: {link}"
            checked += 1
    # Raw CI report artifacts live beside site/, rather than inside it.
    for path in (ROOT / "target/reports").glob("*.html"):
        for link in Document(path.read_text(encoding="utf-8")).links:
            url = urlsplit(link)
            if url.scheme or url.netloc:
                continue
            target = (path.parent / unquote(url.path)).resolve() if url.path else path.resolve()
            assert target.is_relative_to((ROOT / "target").resolve()), f"Report link leaves output: {link}"
            assert target.is_file(), f"Broken artifact link: {path}: {link}"
            if url.fragment and target in documents:
                assert unquote(url.fragment) in documents[target].ids, f"Missing artifact fragment: {link}"
            checked += 1
    for profile in ("items", "records", "datasets", "catalog"):
        graph = Graph()
        for suffix in ("class_definitions", "property_definitions"):
            graph.parse(ROOT / f"{profile}_{suffix}.ttl", format="turtle")
        terms = set(graph.subjects(RDF.type, RDFS.Class)) | set(graph.subjects(RDF.type, RDF.Property))
        document = documents[(SITE / profile / "index.html").resolve()]
        for term in terms:
            anchor = "term-" + hashlib.sha256(str(term).encode()).hexdigest()[:16]
            assert anchor in document.ids, f"Missing reference term {term}"
        for svg in (SITE / profile).glob("*.svg"):
            root = ET.parse(svg).getroot()
            assert root.tag.endswith("svg"), f"Not SVG: {svg}"
            assert "Syntax Error" not in svg.read_text(encoding="utf-8"), f"Broken diagram: {svg}"
    for file in SITE.rglob("*"):
        assert not set(file.parts) & {"Konzepte", "Testdaten", "private-reports"}, f"Private export: {file}"
    manifest = json.loads((SITE / "downloads/manifest.json").read_text(encoding="utf-8"))
    assert len(manifest["profiles"]) == 4
    print(f"Documentation checked: {len(documents)} pages, {checked} local links, complete RDF term coverage.")


if __name__ == "__main__":
    main()
