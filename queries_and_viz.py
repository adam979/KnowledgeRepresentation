import re
from pathlib import Path

import folium
from pyproj import Transformer
from rdflib import Graph, Namespace
from rdflib.namespace import XSD

UHI   = Namespace("https://w3id.org/stuttgart-uhi#")
BOT   = Namespace("https://w3id.org/bot#")
SOSA  = Namespace("http://www.w3.org/ns/sosa/")
GEO   = Namespace("http://www.opengis.net/ont/geosparql#")
ALKIS = Namespace("https://w3id.org/stuttgart-uhi/alkis/")
EX    = Namespace("https://w3id.org/stuttgart-uhi/data/")

BASE_DIR = Path(__file__).resolve().parent
TTL_FILE = BASE_DIR / "stuttgart_buildings.ttl"
MAP_FILE = BASE_DIR / "stuttgart_heat_risk_map.html"

TO_WGS84 = Transformer.from_crs("EPSG:25832", "EPSG:4326", always_xy=True)

SPARQL_PREFIXES = """
PREFIX uhi:  <https://w3id.org/stuttgart-uhi#>
PREFIX bot:  <https://w3id.org/bot#>
PREFIX sosa: <http://www.w3.org/ns/sosa/>
PREFIX geo:  <http://www.opengis.net/ont/geosparql#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
"""


def local_name(uri) -> str:
    text = str(uri)
    return text.rsplit("#", 1)[-1].rstrip("/").rsplit("/", 1)[-1]


def wkt_to_latlon(wkt: str) -> tuple[float, float] | None:
    m = re.search(r"POINT\(([0-9.]+)\s+([0-9.]+)\)", wkt)
    if not m:
        return None
    easting, northing = float(m.group(1)), float(m.group(2))
    lon, lat = TO_WGS84.transform(easting, northing)
    return lat, lon


def run_queries(g: Graph) -> None:
    print("=" * 60)
    print("SPARQL query results")
    print("=" * 60)

    Q1 = SPARQL_PREFIXES + """
    SELECT ?zone
           (COUNT(DISTINCT ?b) AS ?total_bldg)
           (COUNT(DISTINCT ?vb) AS ?vuln_bldg)
           (COUNT(DISTINCT ?obs) AS ?heat_days)
    WHERE {
        ?b a bot:Building ;
           uhi:inAnalysisZone ?zone .

        ?obs a uhi:HeatDayObservation ;
             sosa:hasFeatureOfInterest ?zone .

        OPTIONAL {
            ?vb a uhi:VulnerableBuilding ;
                uhi:inAnalysisZone ?zone .
        }
    }
    GROUP BY ?zone
    ORDER BY DESC(?vuln_bldg)
    """

    print("\nQ1 — Zone risk summary")
    print(f"  {'Zone':<30} {'Total':>6} {'Vuln':>6} {'HeatDays':>9}")
    for row in g.query(Q1):
        print(
            f"  {local_name(row.zone):<30} "
            f"{int(row.total_bldg):>6} "
            f"{int(row.vuln_bldg):>6} "
            f"{int(row.heat_days):>9}"
        )

    Q2 = SPARQL_PREFIXES + """
    SELECT ?zone ?rf (COUNT(DISTINCT ?b) AS ?n)
    WHERE {
        ?b a bot:Building ;
           uhi:inAnalysisZone ?zone ;
           uhi:hasRiskFactor ?rf .
    }
    GROUP BY ?zone ?rf
    ORDER BY ?zone DESC(?n)
    """

    print("\nQ2 — Risk factor count per zone")
    print(f"  {'Zone':<30} {'Risk factor':<25} {'Buildings':>9}")
    for row in g.query(Q2):
        print(
            f"  {local_name(row.zone):<30} "
            f"{local_name(row.rf).replace('Instance', ''):<25} "
            f"{int(row.n):>9}"
        )

    Q3 = SPARQL_PREFIXES + """
    SELECT ?roofLabel (COUNT(?b) AS ?n)
    WHERE {
        ?b a uhi:VulnerableBuilding ;
           uhi:hasRoofType ?rt .
        ?rt rdfs:label ?roofLabel .
        FILTER(LANG(?roofLabel) = "en")
    }
    GROUP BY ?roofLabel
    ORDER BY DESC(?n)
    """

    print("\nQ3 — Roof types of vulnerable buildings")
    for row in g.query(Q3):
        print(f"  {str(row.roofLabel):<30} {int(row.n):>4}")

    Q4_VULN = SPARQL_PREFIXES + """
    SELECT (AVG(?h) AS ?avg_h)
           (AVG(?fp) AS ?avg_fp)
           (MAX(?h) AS ?max_h)
           (MAX(?fp) AS ?max_fp)
    WHERE {
        ?b a uhi:VulnerableBuilding ;
           uhi:hasMeasuredHeight ?h ;
           uhi:hasFootprintArea ?fp .
    }
    """

    Q4_ALL = SPARQL_PREFIXES + """
    SELECT (AVG(?h) AS ?avg_h)
           (AVG(?fp) AS ?avg_fp)
    WHERE {
        ?b a bot:Building ;
           uhi:hasMeasuredHeight ?h ;
           uhi:hasFootprintArea ?fp .
    }
    """

    print("\nQ4 — Geometry stats: vulnerable vs. all buildings")
    for row in g.query(Q4_VULN):
        print(
            f"  Vulnerable — avg height: {float(row.avg_h):.1f} m  "
            f"avg footprint: {float(row.avg_fp):.0f} m²  "
            f"max height: {float(row.max_h):.1f} m  "
            f"max footprint: {float(row.max_fp):.0f} m²"
        )

    for row in g.query(Q4_ALL):
        print(
            f"  All bldgs  — avg height: {float(row.avg_h):.1f} m  "
            f"avg footprint: {float(row.avg_fp):.0f} m²"
        )

    Q5 = SPARQL_PREFIXES + """
    SELECT ?zone
           (MAX(?t) AS ?max_t)
           (COUNT(?obs) AS ?heat_days)
    WHERE {
        ?obs a uhi:HeatDayObservation ;
             sosa:hasFeatureOfInterest ?zone ;
             sosa:hasSimpleResult ?t .
    }
    GROUP BY ?zone
    ORDER BY DESC(?max_t)
    """

    print("\nQ5 — Peak temperature and heat days per zone")
    print(f"  {'Zone':<30} {'Max temp':>9} {'Heat days':>10}")
    for row in g.query(Q5):
        print(
            f"  {local_name(row.zone):<30} "
            f"{float(row.max_t):>8.1f}°C "
            f"{int(row.heat_days):>10}"
        )

    Q6 = SPARQL_PREFIXES + """
    SELECT ?b
           (GROUP_CONCAT(DISTINCT ?factorLabel; separator=", ") AS ?factors)
           (SAMPLE(?h) AS ?height)
           (SAMPLE(?fp) AS ?footprint)
    WHERE {
        ?b a uhi:VulnerableBuilding ;
           uhi:hasRiskFactor ?rf ;
           uhi:hasMeasuredHeight ?h ;
           uhi:hasFootprintArea ?fp .
        OPTIONAL {
            ?rf rdfs:label ?factorLabel .
            FILTER(LANG(?factorLabel) = "en")
        }
    }
    GROUP BY ?b
    ORDER BY DESC(?height)
    LIMIT 15
    """

    print("\nQ6 — Explainability sample: why selected buildings are vulnerable")
    print(f"  {'Building':<24} {'Risk factors':<60} {'Height':>8} {'Footprint':>10}")
    for row in g.query(Q6):
        print(
            f"  {local_name(row.b):<24} "
            f"{str(row.factors):<60} "
            f"{float(row.height):>7.1f}m "
            f"{float(row.footprint):>9.0f}m²"
        )


def risk_factor_labels(g: Graph, building_uri) -> list[str]:
    Q = SPARQL_PREFIXES + """
    SELECT ?label WHERE {
        VALUES ?b { <%s> }
        ?b uhi:hasRiskFactor ?rf .
        OPTIONAL {
            ?rf rdfs:label ?label .
            FILTER(LANG(?label) = "en")
        }
    }
    ORDER BY ?label
    """ % str(building_uri)

    labels = []
    for row in g.query(Q):
        labels.append(str(row.label) if row.label else "Risk factor")
    return labels


def build_map(g: Graph) -> None:
    print("\nBuilding map …")

    Q_MAP = SPARQL_PREFIXES + """
    SELECT ?b ?wkt ?h ?fp ?zone ?vuln
    WHERE {
        ?b a bot:Building ;
           uhi:hasMeasuredHeight ?h ;
           uhi:hasFootprintArea ?fp ;
           uhi:inAnalysisZone ?zone ;
           geo:hasGeometry ?geom .
        ?geom geo:asWKT ?wkt .
        BIND(EXISTS { ?b a uhi:VulnerableBuilding } AS ?vuln)
    }
    """

    ZONE_COLORS = {
        "Zone_513_5402": "#3186cc",
        "Zone_513_5403": "#e07b39",
        "Zone_514_5402": "#5baa57",
        "Zone_514_5403": "#9b5fc0",
    }

    m = folium.Map(
        location=[48.762, 9.179],
        zoom_start=14,
        tiles="CartoDB positron",
    )

    layer_vuln = folium.FeatureGroup(
        name="Vulnerable buildings (reasoning-inferred)",
        show=True,
    )
    layer_normal = folium.FeatureGroup(
        name="Other buildings",
        show=True,
    )

    skipped = 0
    plotted = 0
    vuln_count = 0

    rows = list(g.query(Q_MAP))
    print(f"  Plotting {len(rows)} buildings …")

    for row in rows:
        ll = wkt_to_latlon(str(row.wkt))
        if ll is None:
            skipped += 1
            continue

        lat, lon = ll
        height = float(row.h)
        footprint = float(row.fp)
        zone_id = local_name(row.zone)
        building_id = local_name(row.b)
        is_vulnerable = str(row.vuln).lower() == "true"

        factors_html = ""
        if is_vulnerable:
            factors = risk_factor_labels(g, row.b)
            if factors:
                factors_html = "<br><b>Risk factors:</b><br>" + "<br>".join(
                    f"• {factor}" for factor in factors
                )

        popup_html = (
            f"<b>{building_id}</b><br>"
            f"Height: {height:.1f} m<br>"
            f"Footprint: {footprint:.0f} m²<br>"
            f"Zone: {zone_id}<br>"
            f"<b style='color:{'red' if is_vulnerable else 'gray'}'>"
            f"{'⚠ VulnerableBuilding' if is_vulnerable else 'Normal'}</b>"
            f"{factors_html}"
        )

        if is_vulnerable:
            folium.CircleMarker(
                location=[lat, lon],
                radius=6,
                color="#c0392b",
                fill=True,
                fill_color="#e74c3c",
                fill_opacity=0.85,
                weight=1.5,
                popup=folium.Popup(popup_html, max_width=260),
                tooltip=f"⚠ {building_id} ({height:.0f}m, {footprint:.0f}m²)",
            ).add_to(layer_vuln)
            vuln_count += 1
        else:
            folium.CircleMarker(
                location=[lat, lon],
                radius=2,
                color=ZONE_COLORS.get(zone_id, "#7f8c8d"),
                fill=True,
                fill_color=ZONE_COLORS.get(zone_id, "#7f8c8d"),
                fill_opacity=0.4,
                weight=0.5,
                popup=folium.Popup(popup_html, max_width=220),
            ).add_to(layer_normal)

        plotted += 1

    layer_normal.add_to(m)
    layer_vuln.add_to(m)

    legend_html = """
    <div style="position:fixed;bottom:30px;left:30px;z-index:9999;
                background:white;padding:12px 16px;border-radius:6px;
                border:1px solid #ccc;font-family:sans-serif;font-size:13px;">
      <b>Stuttgart Heat Risk KG</b><br>
      <span style="color:#e74c3c">&#9679;</span> Vulnerable building
            (reasoning-inferred: &#8805;2 risk factors)<br>
      <span style="color:#3186cc">&#9679;</span> Zone 513/5402 (SW)<br>
      <span style="color:#e07b39">&#9679;</span> Zone 513/5403 (NW)<br>
      <span style="color:#5baa57">&#9679;</span> Zone 514/5402 (SE)<br>
      <span style="color:#9b5fc0">&#9679;</span> Zone 514/5403 (NE)<br>
      <br>
      <small>Data: LGL BW LoD2 &bull; Climate: Open-Meteo 2024<br>
      Ontology: BOT + SOSA + GeoSPARQL + uhi:</small>
    </div>
    """
    m.get_root().html.add_child(folium.Element(legend_html))
    folium.LayerControl(collapsed=False).add_to(m)

    m.save(str(MAP_FILE))
    print(f"  Plotted : {plotted} buildings ({vuln_count} vulnerable, {skipped} skipped)")
    print(f"  Map saved: {MAP_FILE.name}")


def main() -> None:
    print("Loading graph …")

    g = Graph()
    for prefix, ns in [
        ("uhi", UHI),
        ("bot", BOT),
        ("sosa", SOSA),
        ("geo", GEO),
        ("alkis", ALKIS),
        ("ex", EX),
        ("xsd", XSD),
    ]:
        g.bind(prefix, ns)

    g.parse(str(TTL_FILE), format="turtle")
    print(f"  {len(g)} triples")

    run_queries(g)
    build_map(g)


if __name__ == "__main__":
    main()