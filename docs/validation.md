# Regeltests

Java 25 und **Apache Jena 6.2.0** – wie in der API. CI: Maven 3.9.11; lokal auch
mit Maven 3.10.0 geprüft. Abhängigkeitsversionen stehen im `pom.xml`. Lokal:

```sh
mvn --batch-mode verify
```

`target/reports/index.html` erklärt die Ergebnisse; daneben liegen standardisierte
SHACL-Berichte als Turtle. JUnit-XML: `target/surefire-reports/`. Die Website kopiert
nur öffentliche Berichte. Generierte Dateien werden nicht eingecheckt.

## Ausführungsvertrag

- Turtle/RDF/XML werden explizit aus lokalen Streams gelesen. `Shapes.parse(Graph)`
  kompiliert die Regeln; `ShaclValidator.validate(...).conforms()` entscheidet.
- Kein Reasoner, kein automatisches Zusammenmischen von Vokabular und Nutzdaten,
  kein Nachladen von `owl:imports`. Auch importierte Vokabulare bleiben offline.
- SHACLs `targetClass` berücksichtigt explizite `rdfs:subClassOf`-Pfade im
  **Datengraphen**. Das ist keine allgemeine RDFS-Inferenz. Klassenaxiome nur im
  Shapes-Graphen erweitern die Daten nicht.
- Jena zählt auch `sh:Warning`-Befunde für `sh:conforms false`. Warnungen werden
  nicht stillschweigend zu Erfolg umgedeutet. RIOT-Parserwarnungen werden wie in der
  API protokolliert; Syntax- und Kompilierungsfehler brechen den Test ab.
- Die API lädt weiterhin nur `items.ttl` und `records.ttl`. Deren fester Target-Knoten
  wird auch bei leerem Datengraphen geprüft: null Triple → Ablehnung; ein beliebiges
  Triple → Erfolg. Die vier fachlichen Entwürfe werden dadurch nicht aktiviert.

## Was die Tests festnageln

30 synthetische Fälle unter `tests/data/` prüfen die vorhandenen Grenzen:

| Profil | Erwartung |
|---|---|
| Items | Proxy: genau ein IRI-Wert für `ore:proxyFor` und `ore:proxyIn`; Aggregation: genau ein IRI-Wert für `edm:aggregatedCHO`. Fehlend, mehrfach, Literal oder Blank Node erzeugen die jeweils konkrete Verletzung. |
| Items, Medientyp | Die fünf vorhandenen EDM-Werte sind zulässig, auch mehrere zugleich. Fehlend ist erlaubt; `UNKNOWN` erzeugt genau ein `sh:Warning`. Sprachmarkierte Titel bleiben zulässig. |
| Records | Ein vorhandenes `bf:adminMetadataFor` muss eine IRI sein. Fehlend und mehrere IRI-Werte bleiben erlaubt. |
| Datasets, Catalog | Vorhandene Distribution-/Dataset-Verweise dürfen IRIs oder Blank Nodes sein. Literalwerte scheitern; fehlende und mehrere Verweise bleiben erlaubt. |
| Aktive API-Policies | Leerer Graph scheitert; beliebiges einzelnes Triple besteht. |

Jeder Fall vergleicht **konkrete** Ressourcen, Property-Pfade, Werte, benannte
Quell-Shapes, Constraint-Komponenten und Schweregrade. Er vergleicht außerdem die
erreichten Shape-/Fokusressourcenpaare. Eigene Negativkontrollen zeigen: Ein
typfreier oder leerer Graph erreicht die fachlichen Targets nicht. Grün ohne Target
ist kein Nachweis fachlicher Gültigkeit. Doppelte RDF-Tripel zählen als ein Wert.

Zusätzliche Tests parsen alle Modellquellen, verlangen aktive benannte NodeShapes,
prüfen die Shape-Kompilierung und sichern die Behandlung kaputten Turtle/SPARQLs,
fehlender Inferenz und nicht nachgeladener Imports ab. Zusammen: 34 Tests.

**Technische Korrektur gegenüber dem Ausgangsstand:** `sh:IRIOrBlankNode` in
Datasets und Catalog war kein gültiger SHACL-Knotenartbezeichner und ließ sich mit
Jena nicht kompilieren. Er wurde durch `sh:BlankNodeOrIRI` ersetzt. Das setzt die
bereits beschriebene Absicht „IRI oder Blank Node“ um; keine neue Pflichtangabe.
Die aktiven API-Policies bleiben unverändert.

## Berichte lesen

Eine erwartete Ablehnung ist ein erfolgreicher Test. Unerwartete Ergebnisse,
fehlende Zielabdeckung und technische Fehler lassen Maven/CI scheitern. Berichte
werden vor den Ergebnisassertionen geschrieben; Actions lädt sie auch bei Fehlern
hoch. Bei einem Parserfehler kann noch kein SHACL-Bericht entstehen – dessen
Fehler steht im JUnit-Bericht.

Jeder RDF-/HTML-Bericht enthält Beispieldatensatz, Profilversion, Quellcommit,
Arbeitsbaumstatus sowie SHA-256 von Policy und Daten. Er enthält Fokus, Property,
Wert, Erklärung, Schweregrad und Regel. Der RDF-Bericht übernimmt auch den
Shapes-Graphen: anonyme Property-Shapes bleiben außerhalb des Testprozesses
auflösbar. Die HTML-Sicht verlinkt zur benannten Regel bzw. zur aktiven Policy.

## Private Beispiele, nur lokal

`Konzepte/` und `Testdaten/` bleiben ignorierte Arbeitsgrundlagen. Optional:

```sh
mvn --batch-mode -DprivateExamples=true test
```

Der Zusatzlauf liest lokale RDF/XML-Dateien und prüft sie gegen alle Profile und
beide API-Policies. Er erwartet Konformität mit den **bisher modellierten** Regeln
und zeigt die tatsächlich erreichten Targets. Er erzeugt ausschließlich private
Beispielberichte unter `target/private-reports/` und legt JUnit-Ausgaben unter
`target/private-surefire-reports/` ab. Öffentliche synthetische Berichte bleiben
unter `target/reports/`; private Ausgaben gehören weder in Pages noch in Artefakte
oder Releases. Keine Tests fordern eine vollständige fachliche EDM-Prüfung vor.
