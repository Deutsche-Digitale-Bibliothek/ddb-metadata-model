# Modell → API

Die API bindet dieses Repository unter
`api-service/src/main/resources/shacl` als Git-Submodul ein. Der Gitlink legt
den Modell-Commit fest. Kein `--remote`, kein Modell-Download beim Build oder
zur Laufzeit.

Nur `items.ttl` und `records.ttl` kommen ins Anwendungs-JAR. Beide prüfen
weiterhin ausschließlich einen nichtleeren Graphen. Die fachlichen
`*_shapes.ttl` bleiben Arbeitsentwürfe; ein Submodul-Update aktiviert sie nicht.

## Bewusst aktualisieren

Im API-Checkout:

```bash
git submodule sync --recursive
git submodule update --init --recursive
git -C api-service/src/main/resources/shacl fetch origin
git -C api-service/src/main/resources/shacl checkout <veröffentlichter-Modell-Commit>
mvn -pl api-service clean verify
python api-service/src/main/resources/shacl/scripts/check_api_resources.py \
  api-service/target/ddb-api-v3-service-0.1.0.jar
git add api-service/src/main/resources/shacl
git commit -m "Update metadata model"
```

Neue Checkouts übernehmen diesen Stand mit `git clone --recurse-submodules`.
Im Maven-POM schließt die allgemeine Ressourcenregel `shacl/**` aus; eine
zweite Regel kopiert nur die beiden aktiven Policies und filtert ihre Bytes nicht.

## Geprüfter Integrationsstand

Am 17.11.2026 wurde ein separater Build des aktuellen API-Arbeitsbaums
(`c39fba6` plus vorhandene Submodul-Migration und Ressourcenbegrenzung) geprüft:

- `clean verify -Dtest=ShaclRdfValidatorTest`: 13 Tests, keine Fehler; Java 25,
  Jena 6.2.0, vollständige Kompilierung und Spring-Boot-JAR.
- Beide Endpunkte lehnen leere Graphen ab und akzeptieren beliebige nichtleere
  Graphen. Die Tests decken auch Startfehler und parallele Validierung ab.
- Der Paketcheck fand exakt `shacl/items.ttl` und `shacl/records.ttl`, jeweils
  bytegleich zur ausgewählten Modellquelle. Eine zusätzliche Werkzeugdatei im
  Submodul wurde nicht eingepackt.

Der damalige Gitlink zeigte auf `c0ddd20fdf69aaa34520cb1c8bfeec1f0c50cda6`.
Die aktiven Policy-Dateien wurden bei der Modell-Erweiterung nicht verändert.
Ein vollständiger API-Systemtest mit laufendem Objektspeicher war nicht Teil
dieses gezielten Integrationsbuilds.
