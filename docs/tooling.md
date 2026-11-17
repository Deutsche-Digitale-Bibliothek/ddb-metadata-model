# Werkzeugprobe: Items

Entscheidung: **Jena 6.2.0 prüft; RDFLib erzeugt die vollständige statische Referenz.**
Keine zusätzlichen OWL-Klassen, Domains oder Ranges für ein hübscheres HTML.

Ausgangspunkt der Probe sind die unveränderten Begriffsdefinitionen,
die annotierten Start-Shapes und `profiles/items.ttl`: **14 `rdfs:Class`,
69 `rdf:Property`, 3 NodeShapes**. Lokale Konzept- und Beispieldateien werden
dabei nicht eingelesen oder veröffentlicht.

| Werkzeug | Konkrete Ausgabe | Konsequenz |
|---|---|---|
| pyLODE 3.2.1, `ontpub` | 69 Property-Einträge, **0 von 14 Klassen**. Mehrsprachige Labels werden teilweise direkt verkettet, etwa „HerstellungsortPlace of manufacture“. Die vorhandene `prof:Profile`-Metadatenwurzel genügt; `owl:Ontology` ist nicht nötig. | Keine vollständige Referenz dieser RDFS-Quellen. Keine zusätzliche Pflichtabhängigkeit. |
| SHACL Play 0.12.6, `doc -l de -nsd` | Alle 3 NodeShapes, deutsche Shape-/Propertytitel, Kardinalitäten und `sh:in`-Liste. Strukturüberschriften bleiben Englisch; der Dokumenttitel bleibt bei diesen Profilmetadaten leer. | Brauchbare zusätzliche Regelsicht, aber kein vollständiges Vokabular. |
| SHACL Play 0.12.6, `draw` | PlantUML-Quelle enthält Proxy, Aggregation und vier Properties. Die SVG-Datei enthält einen **Syntaxfehler**, obwohl der Prozess erfolgreich endet: ein Gruppenabschnitt nutzt den Klassennamen mit Doppelpunkt ohne Anführungszeichen. | Dateiexistenz und Exitcode reichen als Diagrammprüfung nicht. Die kanonischen SVGs werden direkt aus vorhandenen RDF-Beziehungen erzeugt. |
| SHACL Play 0.12.6, `report` | Der echte Jena-Bericht `items-literal.ttl` wird lesbar mit drei Befunden, Ressource, Pfad, Wert, Meldung und Constraint-Komponente dargestellt. Profilversion und Quellcommit aus den Berichtsmetadaten fehlen in dieser HTML-Sicht. | Als Vergleich geeignet. Die veröffentlichte Berichtssicht liest dieselben Jena-Berichte und zeigt zusätzlich Herkunft, erwartetes Ergebnis und Regelverweis. |

Die RDFLib-Sicht zählt alle ausdrücklich dokumentierten Klassen und Properties,
erhält Sprachfassungen getrennt und zeigt sämtliche tatsächlich vorhandenen
Constraints. Diagramme zeigen `rdfs:subClassOf` sowie SHACL-Targets und -Pfade.
Ein aus Fachtexten erfundenes Objektbeziehungsmodell wäre keine weitere
Serialisierung dieser Quellen. WIDOCO wurde deshalb nicht zusätzlich als
Pflichtwerkzeug eingeführt.

## Wiederholen

Optionaler Vergleich, kein zweiter Validator. Vorausgesetzt sind pyLODE 3.2.1,
RDFLib 7.6.0 und der [SHACL-Play-CLI-JAR 0.12.6](https://github.com/sparna-git/shacl-play/releases/tag/0.12.6).
Das [CLI](https://github.com/sparna-git/shacl-play/wiki/Run-SHACL-Play-App-from-command-line)
beschreibt `doc`, `draw` und `report`;
[pyLODE](https://github.com/RDFLib/pyLODE) dokumentiert die Python-Werkzeuge.

```sh
python -m pip install pylode==3.2.1 rdflib==7.6.0
python scripts/evaluate_tools.py --shacl-play-jar target/tools/shacl-play-app-0.12.6-onejar.jar
# Mit einem öffentlichen, von Jena erzeugten Items-Bericht:
python scripts/evaluate_tools.py --report target/reports/items-literal.ttl
```

Unter Windows bei Bedarf `--java "C:\Pfad\zu\java.exe"` ergänzen.
Eingabebundle, HTML, SVG, PlantUML, Prozesslogs und gemessene Abdeckung landen
unter `target/tool-evaluation/`. Keine erzeugte Datei wird nachbearbeitet.

## Sichtprüfung der Erstfassung

17.11.2026: Die tatsächlich erzeugten Items-SVGs wurden mit resvg_py 0.5.0
rasterisiert und visuell geprüft: Beschriftungen, Pfeile und Boxen sind vollständig
und überschneiden sich nicht. Ein Browser war in der Ausführungsumgebung nicht
verfügbar; die HTML-Ansichten sind inhaltlich und auf Links geprüft, eine visuelle
Browserabnahme bleibt offen. Der Rasterizer ist nur ein lokales QA-Werkzeug.
