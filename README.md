# Stuttgart Heat Risk Knowledge Graph

Knowledge graph for score-based urban heat island (UHI) risk assessment in Stuttgart-Mitte. The project integrates LoD2 CityGML building geometry, Open-Meteo climate observations, OpenStreetMap vegetation indicators, and computed heat-risk assessments under a shared RDF/OWL model.

The current model no longer classifies vulnerable buildings with a simple “at least two risk factors” rule. Instead, it represents explicit `uhi:HeatRiskAssessment` instances, assigns `uhi:HeatRiskCategory` values, and classifies buildings as `uhi:VulnerableBuilding` when their building-level heat-risk assessment exceeds the project-defined threshold.

## Overview

The pipeline creates a unified knowledge graph from three data sources:

- **CityGML LoD2**: building geometry, height, footprint, roof type, function, analysis zone
- **Open-Meteo**: 2024 daily maximum temperature observations and heat-day observations using SOSA
- **OpenStreetMap**: vegetation fraction, tree count, and vegetation types per analysis zone

Derived indicators such as Sky View Factor, urban density, basin depth, impervious surface fraction, vegetation fraction, and heat-day count are combined into zone-level and building-level heat-risk assessments.

## Data

**Building geometry source:** LGL Baden-Württemberg — <https://opengeodata.lgl-bw.de>  
**Tiles:** `LoD2_32_513_5402_1_BW`, `LoD2_32_513_5403_1_BW`, `LoD2_32_514_5402_1_BW`, `LoD2_32_514_5403_1_BW`  
**License:** Datenlizenz Deutschland – Namensnennung – Version 2.0 (dl-de/by-2-0)

Place the extracted GML files in:

```text
LoD2_32_513_5402_2_bw/
```

## Installation

Python 3.11+ is recommended.

```bash
python -m venv .venv
source .venv/bin/activate      # macOS/Linux
# .venv\Scripts\activate       # Windows
pip install -r requirements.txt
```

## Pipeline

Run the scripts in order. Each enrichment step reads and writes `stuttgart_buildings.ttl`.

| Step | Script | Purpose |
|---|---|---|
| 1 | `audit.py` | Inspect raw CityGML tiles and report geometry/statistics |
| 2 | `citygml_to_rdf.py` | Convert LoD2 buildings to RDF and create building/zone triples |
| 3 | `climate_data.py` | Add Open-Meteo SOSA observations and heat-day observations |
| 4 | `osm_enrichment.py` | Add OSM vegetation fraction, tree count, and vegetation types |
| 5 | `risk_assessment.py` | Compute zone/building heat-risk assessments and categories |
| 6 | `queries_and_viz.py` | Run SPARQL queries and generate an interactive map |

```bash
python citygml_to_rdf.py
python climate_data.py
python osm_enrichment.py
python risk_assessment.py
python queries_and_viz.py
```

`reasoning.py` is kept as a compatibility wrapper and now delegates to `risk_assessment.py`.

## Ontology

The ontology is stored in `uhi_ontology.ttl` under the namespace:

```text
https://w3id.org/stuttgart-uhi#
```

Core classes:

- `uhi:AnalysisZone`
- `uhi:HeatRiskAssessment`
- `uhi:ZoneHeatRiskAssessment`
- `uhi:BuildingHeatRiskAssessment`
- `uhi:HeatRiskCategory`
- `uhi:VulnerableBuilding`
- `uhi:VegetationType`

Core properties:

- `uhi:hasHeatRiskAssessment`
- `uhi:hasHeatRiskScore`
- `uhi:hasIndicativeDeltaT`
- `uhi:hasRiskCategory`
- `uhi:hasSkyViewFactor`
- `uhi:hasUrbanDensity`
- `uhi:hasBasinDepth`
- `uhi:hasVegetationFraction`
- `uhi:hasTreeCount`
- `uhi:hasImperviousSurfaceFraction`
- `uhi:hasHeatDayCount`

Reused vocabularies:

- BOT for buildings and zones
- GeoSPARQL for geometry
- SOSA for climate observations

## Example SPARQL query

```sparql
PREFIX uhi: <https://w3id.org/stuttgart-uhi#>

SELECT ?building ?category ?score
WHERE {
  ?building uhi:hasHeatRiskAssessment ?assessment .
  ?assessment
      uhi:hasRiskCategory ?category ;
      uhi:hasHeatRiskScore ?score .
  FILTER(?category IN (uhi:HighRisk, uhi:ExtremeRisk))
}
ORDER BY DESC(?score)
```

## Outputs

- `stuttgart_buildings.ttl` — enriched RDF knowledge graph
- `stuttgart_heat_risk_map.html` — interactive Folium map of buildings and risk categories

## Attribution

- Building geometry: © LGL Baden-Württemberg, dl-de/by-2-0
- Climate data: Open-Meteo Historical Weather API, CC BY 4.0
- OSM data: © OpenStreetMap contributors, ODbL
