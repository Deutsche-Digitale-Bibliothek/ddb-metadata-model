# DDB Metadata Model

Vier RDF-Anwendungsprofile der Deutschen Digitalen Bibliothek.
**Arbeitsentwurf 0.1.0.** Die Git-Historie, Autoren und
[Apache-2.0-Lizenz](LICENSE) stammen aus dem bisherigen SHACL-Verzeichnis der
[DDB API v3](https://github.com/mbuechner/ddb-api-v3).

[Repository](https://github.com/Deutsche-Digitale-Bibliothek/ddb-metadata-model) ·
[Dokumentation](https://deutsche-digitale-bibliothek.github.io/ddb-metadata-model/) ·
[Versionen](https://github.com/Deutsche-Digitale-Bibliothek/ddb-metadata-model/releases)

## Zwei Ebenen, bewusst getrennt

| Bereich | Fachlicher Umfang | Aktive API-Policy |
|---|---|---|
| Items | Kulturerbeobjekte, Proxys, Aggregationen, Repräsentationen, Kontext | `items.ttl`: Graph hat mindestens ein Triple |
| Records | Administration, Provenienz, technische Anreicherung, Qualität | `records.ttl`: Graph hat mindestens ein Triple |
| Datasets | Datensets und Distributionen | keine |
| Catalog | Kataloge und Datendienste | keine |

Die API lädt **nur `items.ttl` und `records.ttl`**, einmal beim Start vom
Classpath. Die separaten `*_shapes.ttl` sind fachliche Entwürfe. Ein neues
Submodul-Commit aktiviert sie nicht. Diese Regeln ersetzen keinen vollständigen
EDM-Validator; insbesondere sind Pflichtangaben und weitere fachliche
Konsistenzregeln noch offen.

## Quellen und Sichten

```text
*_class_definitions.ttl     Klassenreferenz (rdfs:Class)
*_property_definitions.ttl  Propertyreferenz (rdf:Property)
*_shapes.ttl               ausführbare Entwurfsregeln
profiles/*.ttl             Titel, Version, Status, Herausgeber, Lizenz
tests/data/                kleine öffentliche Testfälle
src/test/                  Jena-Tests und RDF-/HTML-Berichte
scripts/                   statischer Dokumentationsbuild
target/                    erzeugt und ignoriert
```

Die Turtle-Dateien bleiben für bestehende Verbraucher im Wurzelverzeichnis.
Beschreibungen und Shape-Metadaten werden **im RDF** gepflegt. Die erzeugten
Seiten werden nicht nachbearbeitet. Deutsch wird bevorzugt; vorhandene weitere
Sprachfassungen bleiben sichtbar. Die Referenz erfasst alle Klassen und
Properties, die Regelsicht ausschließlich vorhandene Constraints. Diagramme
zeigen explizite Unterklassenbeziehungen sowie SHACL-Targets und -Pfade.
Domain/Range-Beziehungen werden nicht aus Fachtexten geraten.

JSON-LD und RDF/XML sind weitere Serialisierungen des Profilmodells. Ein
Nutzdaten-Context und JSON Schema sind mögliche spätere Ergänzungen und kein
Ersatz für RDF-/SHACL-/SPARQL-Prüfungen. Es gibt keinen Uploadservice und keinen
zusätzlichen API-Endpunkt.

`Konzepte/` und `Testdaten/` sind private lokale Arbeitsunterlagen. Sie bleiben
ignoriert und außerhalb von Website, Downloads, Releases und öffentlichen
Berichten. CI verwendet ausschließlich `tests/data/`.

## Lokal

Java 25, Maven 3.9.11 und Python 3.13.7; CI pinnt die Werkzeuge und Abhängigkeiten.

```sh
python -m venv .venv
# Linux/macOS: . .venv/bin/activate
# PowerShell: .venv/Scripts/Activate.ps1
python -m pip install -r requirements-docs.txt
mvn --batch-mode verify
python scripts/build_docs.py
python scripts/check_docs.py
python .github/scripts/check_reproducibility.py
python -m http.server 8765 --directory target/site
```

Die Website liegt unter `target/site/`, öffentliche RDF-/HTML-Berichte unter
`target/reports/`, JUnit unter `target/surefire-reports/`.
Erwartete Ablehnungen sind erfolgreiche Tests. Fehlende Targets, andere
Ergebnisse, Syntax- und Ausführungsfehler lassen den Build scheitern.
[Prüfbedingungen und Testfälle](docs/validation.md) ·
[Werkzeugprobe mit Items](docs/tooling.md).

Optionale Prüfung der lokalen RDF/XML-Beispiele:

```sh
mvn verify -DprivateExamples=true
```

Diese Ausgaben landen ausschließlich unter `target/private-reports/` und werden
vom Dokumentationsbuild nicht eingelesen. Vor öffentlichen Builds wieder
`mvn verify` ohne diese Option ausführen.

## CI und Releases

PRs bauen Tests und Dokumentation. RDF-/HTML- und JUnit-Berichte werden auch bei
Testfehlern als Artefakte gesichert. Nur ein erfolgreicher `main`-Build
veröffentlicht die aktuelle Website. Unter **Settings → Pages → Source** muss
einmalig **GitHub Actions** eingestellt sein.

Für einen Release die Versionsangaben in `profiles/*.ttl` und `pom.xml` abstimmen,
einen festen Commit mit `vMAJOR.MINOR.PATCH` taggen und einen GitHub-Release
veröffentlichen. Der Workflow hängt die eigenständige Dokumentation als ZIP,
Manifest und SHA-256-Prüfsummen an. Der Versionsbereich der Website verweist auf
diese unverändert zuordenbaren Archive. Bereits vorhandene Assets werden nicht
überschrieben.

## Modellstand in die API übernehmen

```sh
git clone --recurse-submodules https://github.com/mbuechner/ddb-api-v3.git
cd ddb-api-v3
git -C api-service/src/main/resources/shacl fetch origin
git -C api-service/src/main/resources/shacl checkout <MODELL-COMMIT>
git add api-service/src/main/resources/shacl
```

Anschließend API-Tests und Paketinhalt prüfen, dann den Gitlink committen.
**Kein `submodule update --remote` im Build.** Checkout und Deployment verwenden
den gespeicherten Commit. Maven verpackt aus dem Submodul ausschließlich
`shacl/items.ttl` und `shacl/records.ttl`.
[API-Abnahme und Ressourcenprüfung](docs/api-integration.md).
