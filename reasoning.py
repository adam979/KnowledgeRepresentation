import sys
import shutil
from pathlib import Path

import rdflib
from rdflib import Graph, Namespace, URIRef, Literal
from rdflib.namespace import RDF, RDFS, OWL, XSD

UHI   = Namespace("http://example.org/uhi#")
BOT   = Namespace("https://w3id.org/bot#")
SOSA  = Namespace("http://www.w3.org/ns/sosa/")
GEO   = Namespace("http://www.opengis.net/ont/geosparql#")
ALKIS = Namespace("http://example.org/alkis#")
EX    = Namespace("http://example.org/data#")

TTL_FILE = Path(r"D:\Downloads\AI Lab Project\stuttgart_buildings.ttl")


def reason_with_hermit(ttl_path: Path) -> tuple[list[URIRef], str]:
    import owlready2 as owl2

    # Strip owl:imports so owlready2 doesn't fetch BOT remotely (published as Turtle, which owlready2 can't parse)
    g_tmp = Graph()
    g_tmp.parse(str(ttl_path), format="turtle")
    for s, o in list(g_tmp.subject_objects(OWL.imports)):
        g_tmp.remove((s, OWL.imports, o))

    tmp_xml = TTL_FILE.parent / "_hermit_tmp.owl"
    # Convert to RDF/XML — owlready2 handles XML more reliably than Turtle
    g_tmp.serialize(destination=str(tmp_xml), format="xml")

    # owlready2 on Windows strips "file://" → "/D:/..." (invalid); 2-slash URI strips to valid "D:/..."
    win_uri = "file://" + str(tmp_xml).replace("\\", "/")
    world = owl2.World()
    onto  = world.get_ontology(win_uri).load()

    print("  Running HermiT …", end=" ", flush=True)
    with onto:
        owl2.sync_reasoner(infer_property_values=True, debug=0)
    print("done")

    VB = onto.search_one(iri="*#VulnerableBuilding")
    if VB is None:
        tmp_xml.unlink(missing_ok=True)
        raise RuntimeError("VulnerableBuilding class not found in loaded ontology")

    instances = [URIRef(ind.iri) for ind in VB.instances()]
    tmp_xml.unlink(missing_ok=True)
    return instances, "HermiT (OWL DL)"


# Materialise rdfs:subClassOf chains so SPARQL can count risk factor instances typed as HeatRiskFactor
def _apply_rdfs_subclass_closure(g: Graph) -> None:
    changed = True
    while changed:
        changed = False
        new_triples = []
        for s, _, cls in g.triples((None, RDF.type, None)):
            for _, _, supercls in g.triples((cls, RDFS.subClassOf, None)):
                if (s, RDF.type, supercls) not in g:
                    new_triples.append((s, RDF.type, supercls))
        for triple in new_triples:
            g.add(triple)
            changed = True


SPARQL_INFER = """
PREFIX uhi:  <http://example.org/uhi#>
PREFIX bot:  <https://w3id.org/bot#>

SELECT DISTINCT ?b WHERE {
    ?b a bot:Building ;
       uhi:hasRiskFactor ?rf1 ;
       uhi:hasRiskFactor ?rf2 .
    ?rf1 a uhi:HeatRiskFactor .
    ?rf2 a uhi:HeatRiskFactor .
    FILTER(?rf1 != ?rf2)
}
"""


def reason_with_sparql(g: Graph) -> tuple[list[URIRef], str]:
    print("  Applying RDFS subclass closure …", end=" ", flush=True)
    _apply_rdfs_subclass_closure(g)
    print("done")

    print("  Running SPARQL inference query …", end=" ", flush=True)
    results   = list(g.query(SPARQL_INFER))
    instances = [row.b for row in results]
    print("done")
    return instances, "SPARQL materialisation (RDFS closure + SELECT)"


def materialise(g: Graph, instances: list[URIRef], method: str) -> None:
    for uri in instances:
        g.add((uri, RDF.type, UHI.VulnerableBuilding))

    prov = UHI.VulnerableBuilding_Derivation
    g.add((prov, RDF.type,    OWL.Axiom))
    g.add((prov, RDFS.label,
           Literal(f"VulnerableBuilding derived via: {method}")))
    g.add((prov, RDFS.comment, Literal(
        "Class axiom: uhi:VulnerableBuilding owl:equivalentClass "
        "[ bot:Building AND (>= 2 uhi:hasRiskFactor uhi:HeatRiskFactor) ]. "
        f"Instances materialised using: {method}."
    )))


ZONE_QUERY = """
PREFIX uhi:  <http://example.org/uhi#>
SELECT ?zone (COUNT(DISTINCT ?b) AS ?n) WHERE {
    ?b a uhi:VulnerableBuilding ; uhi:inSubdistrict ?zone .
} GROUP BY ?zone ORDER BY DESC(?n)
"""

COMBO_QUERY = """
PREFIX uhi: <http://example.org/uhi#>
SELECT ?rf1 ?rf2 (COUNT(DISTINCT ?b) AS ?n) WHERE {
    ?b a uhi:VulnerableBuilding ;
       uhi:hasRiskFactor ?rf1 ;
       uhi:hasRiskFactor ?rf2 .
    FILTER(STR(?rf1) < STR(?rf2))
} GROUP BY ?rf1 ?rf2 ORDER BY DESC(?n)
"""

CROSS_QUERY = """
PREFIX uhi:  <http://example.org/uhi#>
PREFIX sosa: <http://www.w3.org/ns/sosa/>
SELECT ?zone
       (COUNT(DISTINCT ?b)   AS ?vuln)
       (COUNT(DISTINCT ?obs) AS ?heat_days)
WHERE {
    ?b   a uhi:VulnerableBuilding ; uhi:inSubdistrict ?zone .
    ?obs a uhi:HeatDayObservation ; sosa:hasFeatureOfInterest ?zone .
} GROUP BY ?zone ORDER BY DESC(?vuln)
"""


def main():
    print("Loading graph …")
    g = Graph()
    g.bind("uhi", UHI)
    g.bind("bot", BOT)
    g.bind("sosa", SOSA)
    g.bind("geo", GEO)
    g.bind("alkis", ALKIS)
    g.bind("ex", EX)
    g.bind("xsd", XSD)
    g.parse(str(TTL_FILE), format="turtle")
    print(f"  {len(g)} triples loaded")

    instances: list[URIRef]
    method:    str

    java_ok = shutil.which("java") is not None
    if java_ok:
        try:
            import owlready2
            print("\nPath A — owlready2 + HermiT (OWL DL reasoner)")
            instances, method = reason_with_hermit(TTL_FILE)
        except Exception as exc:
            print(f"  HermiT failed: {exc}")
            print("\nPath B — SPARQL materialisation fallback")
            instances, method = reason_with_sparql(g)
    else:
        print("\nPath B — SPARQL materialisation (Java not on PATH)")
        instances, method = reason_with_sparql(g)

    if not instances:
        print("ERROR: 0 instances inferred — check ABox and ontology.")
        return

    materialise(g, instances, method)
    g.serialize(destination=str(TTL_FILE), format="turtle")

    n_bldg = sum(1 for _ in g.subjects(RDF.type, BOT.Building))

    print("\n" + "=" * 60)
    print("Reasoning report")
    print("=" * 60)
    print(f"  Inference method           : {method}")
    print(f"  Total buildings            : {n_bldg}")
    print(f"  VulnerableBuilding inferred: {len(instances)}")
    print(f"  Share of building stock    : {100*len(instances)/n_bldg:.1f}%")
    print(f"  Total triples              : {len(g)}")

    print("\nVulnerable buildings per zone:")
    for row in g.query(ZONE_QUERY):
        zone = str(row.zone).split("#")[-1]
        print(f"  {zone:<30} {int(row.n):>4}")

    print("\nRisk factor combinations:")
    for row in g.query(COMBO_QUERY):
        r1 = str(row.rf1).split("#")[-1].replace("Instance", "")
        r2 = str(row.rf2).split("#")[-1].replace("Instance", "")
        print(f"  {r1} + {r2}: {int(row.n)} buildings")

    print("\nCross-layer: vulnerable buildings x heat days per zone:")
    print(f"  {'Zone':<30} {'Vuln':>6} {'HeatDays':>9}")
    print(f"  {'-'*30} {'-'*6} {'-'*9}")
    for row in g.query(CROSS_QUERY):
        zone = str(row.zone).split("#")[-1]
        print(f"  {zone:<30} {int(row.vuln):>6} {int(row.heat_days):>9}")


if __name__ == "__main__":
    main()
