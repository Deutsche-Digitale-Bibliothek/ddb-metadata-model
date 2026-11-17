/* Copyright 2026 Michael Buechner, Deutsche Nationalbibliothek. Apache License 2.0. */
package de.ddb.model;

import static org.junit.jupiter.api.Assertions.*;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.*;
import java.util.stream.Stream;
import org.apache.jena.graph.*;
import org.apache.jena.rdf.model.*;
import org.apache.jena.riot.*;
import org.apache.jena.shacl.*;
import org.apache.jena.shacl.parser.Shape;
import org.apache.jena.shacl.validation.*;
import org.apache.jena.vocabulary.RDF;
import org.junit.jupiter.api.*;

/** Same execution contract as the API: streamed RDF, plain graph, Shapes.parse, conforms(). */
class ModelValidationTest {
    private static final String SH = "http://www.w3.org/ns/shacl#";
    private static final String DDBV = "https://www.deutsche-digitale-bibliothek.de/ddb/validation/";
    private static final String EX = "https://example.org/";
    private static final String ORE = "http://www.openarchives.org/ore/terms/";
    private static final String EDM = "http://www.europeana.eu/schemas/edm/";
    private static final String BF = "http://id.loc.gov/ontologies/bibframe/";
    private static final String DCAT = "http://www.w3.org/ns/dcat#";
    private static final String META = "urn:ddb:model:report:";
    private static final Path REPORTS = Path.of("target", "reports");
    private static final List<Run> RUNS = new ArrayList<>();
    private static final String COMMIT = git("rev-parse", "HEAD");
    private static final boolean DIRTY = !git("status", "--porcelain", "--untracked-files=normal").isBlank();

    record Result(String shape, String focus, String path, String value, String component, String severity) {
        String key() { return String.join(" | ", shape, focus, path, value, component, severity); }
    }
    record Scenario(String id, String profile, String file, String description, Map<String, Set<String>> targets,
                    List<Result> expected) {}
    record Run(String id, String profile, String description, boolean conforms, int results, int targets, boolean expected) {}

    @Test
    void allPublicTurtleParsesAndEveryPolicyCompiles() throws Exception {
        List<Path> files = new ArrayList<>();
        try (var root = Files.list(Path.of("."))) {
            root.filter(p -> p.toString().endsWith(".ttl")).sorted().forEach(files::add);
        }
        try (var profiles = Files.walk(Path.of("profiles"))) {
            profiles.filter(p -> p.toString().endsWith(".ttl")).sorted().forEach(files::add);
        }
        assertTrue(files.size() >= 18, "Die vier Profile und alle Originaldateien müssen gefunden werden");
        for (Path file : files) {
            Graph graph = read(file, Lang.TURTLE);
            assertFalse(graph.isEmpty(), file.toString());
            if (file.getFileName().toString().endsWith("_shapes.ttl") || (file.getParent().equals(Path.of(".")) && Set.of("items.ttl", "records.ttl").contains(file.getFileName().toString()))) {
                Shapes shapes = Shapes.parse(graph);
                assertFalse(shapes.getTargetShapes().isEmpty(), "Policy ohne Targets: " + file);
                for (Shape shape : shapes.getTargetShapes()) {
                    assertFalse(shape.deactivated(), "Ziel-Shape versehentlich deaktiviert: " + file);
                    assertTrue(shape.getShapeNode().isURI(), "Öffentliche NodeShapes brauchen stabile IRIs: " + file);
                    assertTrue(graph.contains(shape.getShapeNode(), RDF.Nodes.type, uri(SH + "NodeShape")));
                }
            }
        }
    }

    @TestFactory
    Stream<DynamicTest> exactRuleResultsAndTargets() {
        return scenarios().stream().map(s -> DynamicTest.dynamicTest(s.id(), () -> run(s)));
    }

    private void run(Scenario s) throws Exception {
        String policy = policy(s.profile());
        Shapes shapes = Shapes.parse(read(Path.of(policy), Lang.TURTLE));
        Graph data = read(Path.of(s.file()), Lang.TURTLE);
        Map<String, Set<String>> actualTargets = new TreeMap<>();
        for (Shape shape : shapes.getTargetShapes()) {
            Set<String> nodes = new TreeSet<>();
            VLib.focusNodes(data, shape).forEach(n -> nodes.add(node(n)));
            actualTargets.put(shape.getShapeNode().getURI(), nodes);
        }
        ValidationReport report = ShaclValidator.get().validate(shapes, data);
        List<Result> actual = report.getEntries().stream().map(e -> result(e, shapes)).toList();
        List<String> expectedKeys = s.expected().stream().map(Result::key).sorted().toList();
        List<String> actualKeys = actual.stream().map(Result::key).sorted().toList();
        boolean expected = actualKeys.equals(expectedKeys) && actualTargets.equals(s.targets()) && report.conforms() == s.expected().isEmpty();
        // Write before asserting: unexpected conformance/results remain inspectable as CI artifacts.
        writeReport(REPORTS, s.id(), s.profile(), s.file(), s.description(), report, shapes,
                actualTargets, s.expected().isEmpty(), expected);
        RUNS.add(new Run(s.id(), s.profile(), s.description(), report.conforms(), actual.size(),
                actualTargets.values().stream().mapToInt(Set::size).sum(), expected));
        assertAll(s.id(),
                () -> assertEquals(s.targets(), actualTargets, "Exakte Zielabdeckung; ein grüner Lauf ohne Zielknoten reicht nicht"),
                () -> assertEquals(expectedKeys, actualKeys, "Focus, Property, Wert, Regel, Komponente und Severity"),
                () -> assertEquals(s.expected().isEmpty(), report.conforms(), "Jena zählt auch Warning-Ergebnisse für conforms()"),
                () -> assertTrue(report.getEntries().stream().allMatch(e -> e.source() != null && e.message() != null), "Jeder Befund braucht Regel und Erklärung"));
    }

    @Test
    void targetSelectionUsesOnlyTheProvidedGraphAndNeverFetchesImports() {
        // A subclass axiom in the shapes graph must not leak into the data graph.
        String shapeText = "@prefix sh: <" + SH + "> . @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> . "
                + "@prefix owl: <http://www.w3.org/2002/07/owl#> . @prefix ex: <https://example.org/> . "
                + "ex:Shape a sh:NodeShape ; sh:targetClass ex:Parent ; sh:class ex:Required ; "
                + "owl:imports <http://127.0.0.1:8089/must-never-be-read> . ex:Child rdfs:subClassOf ex:Parent .";
        Shapes shapes = Shapes.parse(RDFParser.fromString(shapeText, Lang.TURTLE).toGraph());
        Graph data = RDFParser.fromString("<https://example.org/subject> a <https://example.org/Child> .", Lang.TURTLE).toGraph();
        Shape shape = shapes.getShape(uri(EX + "Shape"));
        assertTrue(VLib.focusNodes(data, shape).isEmpty());
        assertTrue(ShaclValidator.get().validate(shapes, data).conforms());
        data.add(Triple.create(uri(EX + "Child"), uri("http://www.w3.org/2000/01/rdf-schema#subClassOf"), uri(EX + "Parent")));
        assertEquals(Set.of(uri(EX + "subject")), new HashSet<>(VLib.focusNodes(data, shape)), "SHACL targetClass follows explicit rdfs:subClassOf in data without a reasoner");
        assertFalse(ShaclValidator.get().validate(shapes, data).conforms());
        assertFalse(data.contains(uri(EX + "subject"), RDF.Nodes.type, uri(EX + "Parent")), "Kein materialisierender RDFS-Reasoner");
    }

    @Test
    void malformedShapesAndSyntaxAreTechnicalErrors() {
        assertThrows(RiotException.class, () -> RDFParser.fromString("<urn:test:x> <urn:test:y> [", Lang.TURTLE)
                .errorHandler(org.apache.jena.riot.system.ErrorHandlerFactory.errorHandlerStrictNoLogging).toGraph());
        Graph malformed = RDFParser.fromString("@prefix sh: <" + SH + "> . <urn:test:shape> a sh:NodeShape ; sh:targetNode <urn:test:x> ; sh:sparql [ sh:select \"NOT SPARQL\" ] .", Lang.TURTLE).toGraph();
        assertThrows(RuntimeException.class, () -> Shapes.parse(malformed));
    }

    @Test
    void localPrivateExamplesAreOptIn() throws Exception {
        if (!Boolean.getBoolean("privateExamples")) return;
        Path input = Path.of("Testdaten");
        assertTrue(Files.isDirectory(input), "Private Testdaten fehlen lokal");
        List<Path> files;
        try (var paths = Files.list(input)) { files = paths.filter(p -> p.toString().endsWith(".xml")).sorted().toList(); }
        assertFalse(files.isEmpty(), "Keine privaten RDF/XML-Beispiele gefunden");
        Path output = Path.of("target", "private-reports");
        List<String> reportIds = new ArrayList<>();
        int index = 0;
        for (Path file : files) {
            Graph data = read(file, Lang.RDFXML);
            assertFalse(data.isEmpty());
            int sample = ++index;
            for (String profile : List.of("items", "records", "datasets", "catalog", "api-items", "api-records")) {
                Shapes shapes = Shapes.parse(read(Path.of(policy(profile)), Lang.TURTLE));
                ValidationReport report = ShaclValidator.get().validate(shapes, data);
                Map<String, Set<String>> targets = new TreeMap<>();
                for (Shape shape : shapes.getTargetShapes()) {
                    Set<String> nodes = new TreeSet<>();
                    VLib.focusNodes(data, shape).forEach(n -> nodes.add(node(n)));
                    targets.put(shape.getShapeNode().getURI(), nodes);
                }
                String id = "local-" + sample + "-" + profile;
                reportIds.add(id);
                writeReport(output, id, profile, file.toString(),
                        "Lokale Plausibilisierung des Arbeitsentwurfs; keine vollständige fachliche Konformitätsaussage. Ein Profil ohne erreichte Targets prüft keine fachlichen Ressourcen.",
                        report, shapes, targets, true, report.conforms());
                assertTrue(report.conforms(), "Das lokale Beispiel soll die modellierten Regeln erfüllen; Details ausschließlich im privaten Bericht");
            }
        }
        StringBuilder html = new StringBuilder(header("Private lokale Beispielberichte"));
        html.append("<p>Nur lokal. Diese Berichte und private-surefire-reports/ werden nicht veröffentlicht.</p><ul>");
        for (String id : reportIds) html.append("<li><a href=\"").append(id).append(".html\">").append(id).append("</a></li>");
        Files.writeString(output.resolve("index.html"), html.append("</ul></main></body></html>"));
    }

    @AfterAll
    static void reportIndex() throws IOException {
        Files.createDirectories(REPORTS);
        StringBuilder html = new StringBuilder(header("Regeltests – synthetische Beispiele"));
        html.append("<p>Jena 6.2.0 · Quellcommit <code>").append(escape(COMMIT)).append("</code>")
                .append(DIRTY ? " · Arbeitsbaum mit Änderungen" : "").append("</p>")
                .append("<p>Ein erwarteter Verstoß ist ein erfolgreicher Test. <code>sh:Warning</code> zählt bei Jena für <code>conforms()</code>. Kein Reasoner; keine externen Imports.</p>")
                .append("<table><thead><tr><th>Beispiel</th><th>Profil</th><th>Beschreibung</th><th>Konform</th><th>Befunde</th><th>Zielpaare</th><th>Erwartung</th></tr></thead><tbody>");
        for (Run run : RUNS.stream().sorted(Comparator.comparing(Run::id)).toList()) {
            html.append("<tr><td><a href=\"").append(run.id()).append(".html\">").append(run.id()).append("</a></td><td>")
                    .append(run.profile()).append("</td><td>").append(escape(run.description())).append("</td><td>")
                    .append(run.conforms()).append("</td><td>").append(run.results()).append("</td><td>")
                    .append(run.targets()).append("</td><td>").append(run.expected() ? "erfüllt" : "FEHLER").append("</td></tr>");
        }
        html.append("</tbody></table><p>RDF-Berichte: pro Beispiel als Turtle verlinkt. JUnit-XML liegt im Build-Artefakt unter surefire-reports/.</p></main></body></html>");
        Files.writeString(REPORTS.resolve("index.html"), html);
    }

    private static void writeReport(Path directory, String id, String profile, String dataset, String description,
                                    ValidationReport report, Shapes shapes, Map<String, Set<String>> targets,
                                    boolean expectedConforms, boolean expectationMet) throws Exception {
        Files.createDirectories(directory);
        Model model = report.getModel();
        // Keep anonymous property shapes resolvable in the standalone standard report.
        // No data triples are copied here; only this policy's source graph.
        model.add(ModelFactory.createModelForGraph(shapes.getGraph()));
        Resource resource = report.getResource();
        model.setNsPrefix("build", META);
        resource.addLiteral(model.createProperty(META + "dataset"), dataset)
                .addLiteral(model.createProperty(META + "profile"), profile)
                .addLiteral(model.createProperty(META + "profileVersion"), version(profile))
                .addLiteral(model.createProperty(META + "sourceCommit"), COMMIT)
                .addLiteral(model.createProperty(META + "workingTreeDirty"), DIRTY)
                .addLiteral(model.createProperty(META + "policySha256"), sha256(Path.of(policy(profile))))
                .addLiteral(model.createProperty(META + "datasetSha256"), sha256(Path.of(dataset)))
                .addLiteral(model.createProperty(META + "expectedConforms"), expectedConforms)
                .addLiteral(model.createProperty(META + "expectationMet"), expectationMet)
                .addLiteral(model.createProperty(META + "jenaVersion"), "6.2.0");
        for (var target : targets.entrySet()) for (String focus : target.getValue()) {
            Resource coverage = model.createResource();
            resource.addProperty(model.createProperty(META + "targetCoverage"), coverage);
            coverage.addProperty(model.createProperty(META + "shape"), model.createResource(target.getKey()));
            coverage.addLiteral(model.createProperty(META + "focusNode"), focus);
        }
        try (var stream = Files.newOutputStream(directory.resolve(id + ".ttl"))) { RDFDataMgr.write(stream, model, RDFFormat.TURTLE_PRETTY); }
        StringBuilder html = new StringBuilder(header(id));
        html.append("<p><a href=\"index.html\">Alle Berichte</a> · <a href=\"").append(id).append(".ttl\">RDF-Bericht (Turtle)</a></p>")
                .append("<p>").append(escape(description)).append("</p><dl><dt>Beispieldatensatz</dt><dd><code>").append(escape(dataset))
                .append("</code></dd><dt>Profil</dt><dd>").append(profile).append(" · ").append(escape(version(profile)))
                .append("</dd><dt>Quellcommit</dt><dd><code>").append(escape(COMMIT)).append("</code>").append(DIRTY ? " (Arbeitsbaum geändert)" : "")
                .append("</dd><dt>Ergebnis</dt><dd>Konform: ").append(report.conforms()).append(" · Erwartet: ").append(expectedConforms)
                .append(" · Testerwartung ").append(expectationMet ? "erfüllt" : "FEHLGESCHLAGEN")
                .append("</dd><dt>Policy SHA-256</dt><dd><code>").append(sha256(Path.of(policy(profile)))).append("</code></dd></dl>");
        if (report.getEntries().isEmpty()) html.append("<p>Keine Validierungsbefunde. Die folgende Zielabdeckung zeigt, welche Ressourcen tatsächlich geprüft wurden.</p>");
        else {
            html.append("<table><thead><tr><th>Ressource</th><th>Eigenschaft</th><th>Wert</th><th>Schwere</th><th>Erklärung</th><th>Regel / Constraint</th></tr></thead><tbody>");
            for (ReportEntry entry : report.getEntries().stream().sorted(Comparator.comparing(e -> result(e, shapes).key())).toList()) {
                Result row = result(entry, shapes);
                String name = row.shape().substring(row.shape().lastIndexOf('/') + 1);
                String prefix = "../site/";
                String href = profile.startsWith("api-")
                        ? prefix + profile.substring(4) + "/downloads/" + profile.substring(4) + "-api-policy.ttl"
                        : prefix + profile + "/index.html#shape-" + name;
                html.append("<tr><td><code>").append(escape(row.focus())).append("</code></td><td><code>").append(escape(row.path()))
                        .append("</code></td><td><code>").append(escape(row.value())).append("</code></td><td>").append(escape(row.severity()))
                        .append("</td><td>").append(escape(entry.message())).append("</td><td><a href=\"").append(escape(href)).append("\">")
                        .append(escape(row.shape())).append("</a><br><code>").append(escape(row.component())).append("</code></td></tr>");
            }
            html.append("</tbody></table>");
        }
        html.append("<h2>Tatsächliche Zielabdeckung</h2><ul>");
        for (var target : targets.entrySet()) html.append("<li><code>").append(escape(target.getKey())).append("</code>: ")
                .append(target.getValue().isEmpty() ? "keine Zielressource" : escape(String.join(", ", target.getValue()))).append("</li>");
        html.append("</ul></main></body></html>");
        Files.writeString(directory.resolve(id + ".html"), html);
    }

    private static List<Scenario> scenarios() {
        List<Scenario> cases = new ArrayList<>();
        Map<String, Set<String>> items = targets("ItemProxyShape", "proxy", "ItemTypeShape", "proxy", "ItemAggregationShape", "aggregation");
        cases.add(new Scenario("items-valid", "items", "tests/data/items-valid.ttl", "Genau ein IRI-Verweis pro Pflichtbeziehung; gültiger Medientyp.", items, List.of()));
        cases.add(new Scenario("items-optional", "items", "tests/data/items-optional.ttl", "edm:type ist optional; deutsche und englische Titel bleiben zulässig.", items, List.of()));
        for (String kind : List.of("missing", "multiple", "literal", "blank")) {
            String component = switch (kind) { case "missing" -> "MinCount"; case "multiple" -> "MaxCount"; default -> "NodeKind"; };
            String cho = kind.equals("blank") ? "_:blank" : kind.equals("literal") ? "\"cho\"" : "—";
            String aggregation = kind.equals("blank") ? "_:blank" : kind.equals("literal") ? "\"aggregation\"" : "—";
            cases.add(new Scenario("items-" + kind, "items", "tests/data/items-" + kind + ".ttl", "Grenzfall " + kind + " für alle drei Pflichtbeziehungen.", items,
                    List.of(expected("ItemProxyShape", "proxy", ORE + "proxyFor", cho, component, "Violation"),
                            expected("ItemProxyShape", "proxy", ORE + "proxyIn", aggregation, component, "Violation"),
                            expected("ItemAggregationShape", "aggregation", EDM + "aggregatedCHO", cho, component, "Violation"))));
        }
        cases.add(new Scenario("items-warning", "items", "tests/data/items-warning.ttl", "Unbekannter Medientyp: ein Warning-Befund; Jena meldet conforms=false.", items,
                List.of(expected("ItemTypeShape", "proxy", EDM + "type", "\"UNKNOWN\"", "In", "Warning"))));
        cases.add(new Scenario("items-types", "items", "tests/data/items-types.ttl", "Alle fünf EDM-Medientypen sind zulässig; edm:type besitzt keine Obergrenze. Doppelte RDF-Tripel zählen nur einmal.", items, List.of()));
        for (String profile : List.of("records", "datasets", "catalog")) {
            String shape = switch (profile) { case "records" -> "RecordAdminLinkShape"; case "datasets" -> "DatasetDistributionLinkShape"; default -> "CatalogDatasetLinkShape"; };
            String focus = switch (profile) { case "records" -> "record"; case "datasets" -> "dataset"; default -> "catalog"; };
            String property = switch (profile) { case "records" -> BF + "adminMetadataFor"; case "datasets" -> DCAT + "distribution"; default -> DCAT + "dataset"; };
            String value = switch (profile) { case "records" -> "item"; case "datasets" -> "distribution"; default -> "dataset"; };
            Map<String, Set<String>> coverage = targets(shape, focus);
            cases.add(new Scenario(profile + "-valid", profile, "tests/data/" + profile + "-valid.ttl", "Mehrere zulässige Verweise; keine erfundene Obergrenze.", coverage, List.of()));
            cases.add(new Scenario(profile + "-optional", profile, "tests/data/" + profile + "-optional.ttl", "Fehlende optionale Verknüpfung bleibt gültig.", coverage, List.of()));
            cases.add(new Scenario(profile + "-literal", profile, "tests/data/" + profile + "-literal.ttl", "Ein Literal verletzt die bestehende NodeKind-Bedingung.", coverage,
                    List.of(expected(shape, focus, property, "\"" + value + "\"", "NodeKind", "Violation"))));
            if (profile.equals("records")) cases.add(new Scenario("records-blank", profile, "tests/data/records-blank.ttl", "Blank Node ist beim IRI-Verweis unzulässig.", coverage,
                    List.of(expected(shape, focus, property, "_:blank", "NodeKind", "Violation"))));
        }
        for (String profile : List.of("items", "records", "datasets", "catalog")) {
            Map<String, Set<String>> emptyTargets = new TreeMap<>();
            (profile.equals("items") ? items.keySet() : targets(switch(profile) { case "records" -> "RecordAdminLinkShape"; case "datasets" -> "DatasetDistributionLinkShape"; default -> "CatalogDatasetLinkShape"; }, "unused").keySet())
                    .forEach(name -> emptyTargets.put(name, Set.of()));
            cases.add(new Scenario(profile + "-unrelated", profile, "tests/data/unrelated.ttl", "Kein passendes rdf:type: keine Zielressource, daher keine Fachprüfung.", emptyTargets, List.of()));
            cases.add(new Scenario(profile + "-empty", profile, "tests/data/empty.ttl", "Entwurf ohne Zielknoten akzeptiert auch einen leeren Graphen.", emptyTargets, List.of()));
        }
        for (String endpoint : List.of("items", "records")) {
            String shape = "urn:ddb:shapes:" + endpoint + ":NonEmptyGraph";
            Map<String, Set<String>> coverage = Map.of(shape, Set.of("urn:ddb:validation:graph"));
            cases.add(new Scenario("api-" + endpoint + "-empty", "api-" + endpoint, "tests/data/empty.ttl", "Aktive API-Policy: fester Target-Knoten erreicht auch den leeren Graphen.", coverage,
                    List.of(new Result(shape, "urn:ddb:validation:graph", "—", "urn:ddb:validation:graph", SH + "SPARQLConstraintComponent", SH + "Violation"))));
            cases.add(new Scenario("api-" + endpoint + "-nonempty", "api-" + endpoint, "tests/data/unrelated.ttl", "Aktive API-Policy akzeptiert ein beliebiges Triple ohne DDB-Fachmodell.", coverage, List.of()));
        }
        return cases;
    }

    private static Map<String, Set<String>> targets(String... pairs) {
        Map<String, Set<String>> targets = new TreeMap<>();
        for (int i = 0; i < pairs.length; i += 2) targets.put(DDBV + pairs[i], Set.of(EX + pairs[i + 1]));
        return targets;
    }
    private static Result expected(String shape, String focus, String path, String value, String component, String severity) {
        return new Result(DDBV + shape, EX + focus, path, value, SH + component + "ConstraintComponent", SH + severity);
    }
    private static Result result(ReportEntry entry, Shapes shapes) {
        Node source = entry.source();
        if (!source.isURI()) {
            var parent = shapes.getGraph().find(Node.ANY, uri(SH + "property"), source);
            if (parent.hasNext()) source = parent.next().getSubject();
            parent.close();
        }
        String path = entry.resultPath() == null ? "—" : entry.resultPath().toString();
        if (path.startsWith("<") && path.endsWith(">")) path = path.substring(1, path.length() - 1);
        return new Result(node(source), node(entry.focusNode()), path, node(entry.value()),
                node(entry.sourceConstraintComponent()), node(entry.severity().level()));
    }
    private static String policy(String profile) { return profile.startsWith("api-") ? profile.substring(4) + ".ttl" : profile + "_shapes.ttl"; }
    private static Graph read(Path path, Lang lang) throws IOException {
        Graph graph = GraphMemFactory.createDefaultGraph();
        try (InputStream input = Files.newInputStream(path)) { RDFDataMgr.read(graph, input, lang); }
        return graph;
    }
    private static String version(String profile) throws IOException {
        Model metadata = ModelFactory.createModelForGraph(read(Path.of("profiles", profile.replace("api-", "") + ".ttl"), Lang.TURTLE));
        var versions = metadata.listObjectsOfProperty(metadata.createProperty("http://purl.org/dc/terms/hasVersion"));
        if (!versions.hasNext()) throw new IllegalStateException("Profilversion fehlt: " + profile);
        String version = versions.next().asLiteral().getString();
        if (versions.hasNext()) throw new IllegalStateException("Mehrdeutige Profilversion: " + profile);
        return version;
    }
    private static String node(Node node) {
        if (node == null) return "—";
        if (node.isURI()) return node.getURI();
        if (node.isBlank()) return "_:blank";
        if (node.isLiteral() && node.getLiteralLanguage().isEmpty() && node.getLiteralDatatypeURI().equals("http://www.w3.org/2001/XMLSchema#string")) return "\"" + node.getLiteralLexicalForm() + "\"";
        return node.toString();
    }
    private static Node uri(String iri) { return NodeFactory.createURI(iri); }
    private static String sha256(Path path) throws Exception { return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(Files.readAllBytes(path))); }
    private static String git(String... args) {
        try {
            List<String> command = new ArrayList<>(List.of("git"));
            command.addAll(List.of(args));
            Process process = new ProcessBuilder(command).redirectErrorStream(true).start();
            String output = new String(process.getInputStream().readAllBytes(), StandardCharsets.UTF_8).strip();
            if (process.waitFor() != 0) throw new IllegalStateException(output);
            return output;
        } catch (Exception exception) { throw new IllegalStateException("Quellcommit nicht bestimmbar", exception); }
    }
    private static String escape(String value) { return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\"", "&quot;"); }
    private static String header(String title) {
        return "<!doctype html><html lang=\"de\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width\"><title>" + escape(title)
                + "</title><style>body{font:16px/1.55 system-ui,sans-serif;color:#172a38;background:#f6f8fa;margin:0}main{max-width:1200px;margin:auto;padding:2rem}a{color:#006c80}h1{line-height:1.2}table{border-collapse:collapse;width:100%;background:white}th,td{text-align:left;border:1px solid #ced7dd;padding:.6rem;vertical-align:top}code{font-size:.85em;overflow-wrap:anywhere}dt{font-weight:bold;margin-top:.5rem}dd{margin-left:0}td{overflow-wrap:anywhere}</style></head><body><main><h1>" + escape(title) + "</h1>";
    }
}
