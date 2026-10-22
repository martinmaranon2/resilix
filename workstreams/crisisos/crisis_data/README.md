# CrisisOS Switzerland — Data Integration Documentation (12 Sources)

This directory houses the complete data integration subsystem for **CrisisOS**, an autonomous, multimodal disaster intelligence and emergency coordination platform focused on Switzerland (specifically hydrological risks and emergency response across Canton Zurich).

---

## Table of Contents

1. [Architecture & Design Overview](#1-architecture--design-overview)
2. [Data Source Catalog (All 12 Integrations)](#2-data-source-catalog-all-12-integrations)
   - [1. Open-Meteo Weather API](#1-open-meteo-weather-api)
   - [2. BAFU / FOEN Swiss Hydrology](#2-bafu--foen-swiss-hydrology)
   - [3. Windy Webcams API V3](#3-windy-webcams-api-v3)
   - [4. swisstopo / Swiss Federal Geodata](#4-swisstopo--swiss-federal-geodata)
   - [5. MeteoSwiss SwissMetNet Stations](#5-meteoswiss-swissmetnet-stations)
   - [6. MeteoSwiss Precipitation Radar](#6-meteoswiss-precipitation-radar)
   - [7. OpenStreetMap Overpass (Infrastructure)](#7-openstreetmap-overpass-infrastructure)
   - [8. ASTRA Road Traffic (opentransportdata.swiss)](#8-astra-road-traffic-opentransportdataswiss)
   - [9. Swiss Flood Hazard Maps (BAFU Aquaprotect)](#9-swiss-flood-hazard-maps-bafu-aquaprotect)
   - [10. Official Swiss Hazard Warnings (natural-hazards.ch)](#10-official-swiss-hazard-warnings-natural-hazardsch)
   - [11. ETH Swiss Seismological Service (SED)](#11-eth-swiss-seismological-service-sed)
   - [12. Swiss Population and Building Data (BFS)](#12-swiss-population-and-building-data-bfs)
3. [Health Status Matrix](#3-health-status-matrix)
4. [Running the Integration Smoke Tests](#4-running-the-integration-smoke-tests)
5. [Exposing Data to the Gemini Reasoning Agent](#5-exposing-data-to-the-gemini-reasoning-agent)

---

## 1. Architecture & Design Overview

Each integration follows a uniform, production-ready pattern:

- **Centralized Configuration**: All URLs, coordinate defaults, timeouts, and model parameters reside in `crisis_data/config.py`.
- **Function Call Auditing**: Every entry point is decorated with `@log_function_call` (`crisis_data/logger.py`) to log arguments, execution duration, and outcomes, stripping large binary payloads.
- **Strict Data Modeling**: Returned payloads conform to standardized typed dataclasses in `crisis_data/models.py`.
- **Fault-Tolerant Fallbacks**: Where keys are missing or services intermittent, informative fallback models (`is_simulated=True`) maintain pipeline stability without crashing agent loops.

---

## 2. Data Source Catalog (All 12 Integrations)

### 1. Open-Meteo Weather API

- **Purpose**: Provides real-time weather observations, precipitation accumulation, and short-term meteorological forecasts.
- **API Endpoint**: `https://api.open-meteo.com/v1/forecast`
- **Documentation**: [https://open-meteo.com/en/docs](https://open-meteo.com/en/docs)
- **Authentication**: None required for noncommercial use.
- **Available Fields**: `temperature_2m`, `precipitation`, `rain`, `showers`, `wind_speed_10m`, `wind_direction_10m`, `hourly` 48-hour forecasts.
- **Update Frequency**: Live model runs (every 15–60 minutes).
- **Code Usage**:
  ```python
  from crisis_data.open_meteo import get_weather
  weather = get_weather(latitude=47.3769, longitude=8.5417)
  ```
- **Test Result & Status**: **`WORKING`** (Response validated in 0.64s; retrieved 14.1°C, 0.1mm precip, 3.4mm 24h accumulation).

---

### 2. BAFU / FOEN Swiss Hydrology

- **Purpose**: Real-time river water levels, discharge volumes, and water temperatures across Swiss river systems, focused on the Sihl and Limmat in Zurich.
- **API Endpoint**: `https://data.bafu.admin.ch/api` (GraphQL)
- **Documentation**: [https://data.bafu.admin.ch/en/](https://data.bafu.admin.ch/en/)
- **Authentication**: None (public GraphQL endpoint).
- **Available Fields**: `stationNo`, `riverName`, `coordinates`, `W` (water level in m a.s.l.), `Q` (discharge in m³/s), `WT` (water temperature in °C).
- **Update Frequency**: Every 10 minutes.
- **Code Usage**:
  ```python
  from crisis_data.bafu_hydro import get_river_measurements, get_river_stations
  stations = get_river_stations()
  measurements = get_river_measurements(station_id="2176")  # Zurich Sihlhölzli
  ```
- **Test Result & Status**: **`WORKING`** (Discovered 3 Zurich stations; retrieved live Sihl readings: Level 412.316 m a.s.l., Discharge 4.339 m³/s).

---

### 3. Windy Webcams API V3

- **Purpose**: Multimodal visual intelligence to detect river overflowing, bridge inundation, and street conditions via public webcams.
- **API Endpoint**: `https://api.windy.com/webcams/api/v3/webcams`
- **Documentation**: [https://api.windy.com/webcams/docs](https://api.windy.com/webcams/docs)
- **Authentication**: Required (`x-windy-api-key: YOUR_API_KEY` via `WINDY_API_KEY` in `.env`). Register at [https://api.windy.com/](https://api.windy.com/).
- **Available Fields**: `webcamId`, `title`, `coordinates`, `status`, `images.current.preview`, `last_updated_at`.
- **Update Frequency**: 15 minutes to 1 hour depending on camera provider.
- **Code Usage**:
  ```python
  from crisis_data.windy_webcams import get_nearby_webcams, get_webcam_image
  cams = get_nearby_webcams(latitude=47.3769, longitude=8.5417, radius_km=15)
  img_data = get_webcam_image(camera_id=cams[0]["camera_id"], image_url=cams[0]["image_url"])
  ```
- **Test Result & Status**: **`WORKING`** (Retrieved 10 live cameras in Canton Zurich with working image URLs).

---

### 4. swisstopo / Swiss Federal Geodata

- **Purpose**: Precise digital elevation model (DEM) querying, LV95 (EPSG:2056) $\leftrightarrow$ WGS84 (EPSG:4326) coordinate transformations, and official Geoportal map links.
- **API Endpoint**: `https://api3.geo.admin.ch/rest/services/height`
- **Documentation**: [https://docs.geo.admin.ch/](https://docs.geo.admin.ch/)
- **Authentication**: None (public federal geodata service).
- **Available Fields**: `elevation_m` (meters above sea level), `lv95_east`, `lv95_north`, `geoportal_url`.
- **Update Frequency**: Static high-accuracy federal DEM (swissALTI3D).
- **Code Usage**:
  ```python
  from crisis_data.swisstopo import get_elevation, wgs84_to_lv95
  elev = get_elevation(latitude=47.3769, longitude=8.5417)
  ```
- **Test Result & Status**: **`WORKING`** (Coordinate transformation verified: (47.3769, 8.5417) $\leftrightarrow$ LV95 (2683304, 1247925); elevation returned 408.4 m a.s.l.).

---

### 5. MeteoSwiss SwissMetNet Stations

- **Purpose**: High-precision 10-minute ground meteorological measurements from federal automated weather stations (`sma` Zurich/Fluntern, `reh` Affoltern, `klo` Kloten).
- **API Endpoint**: `https://data.geo.admin.ch/ch.meteoschweiz.ogd-smn/`
- **Documentation**: [https://opendatadocs.meteoswiss.ch/](https://opendatadocs.meteoswiss.ch/)
- **Authentication**: None (OGD open data).
- **Available Fields**: `temperature_c`, `humidity_percent`, `precipitation_10min_mm`, `wind_speed_ms`, `wind_gust_ms`, `timestamp`.
- **Update Frequency**: Every 10 minutes.
- **Code Usage**:
  ```python
  from crisis_data.meteoswiss_smn import get_weather_stations, get_meteoswiss_observation
  stations = get_weather_stations(radius_km=30)
  obs = get_meteoswiss_observation("sma")
  ```
- **Test Result & Status**: **`WORKING`** (Retrieved live Fluntern observation: 12.0°C, 98.5% humidity, 0.1mm precip, 3.0m/s wind).

---

### 6. MeteoSwiss Precipitation Radar

- **Purpose**: National precipitation radar composite discovery via SpatioTemporal Asset Catalog (STAC).
- **API Endpoint**: `https://data.geo.admin.ch/api/stac/v1/collections/ch.meteoschweiz.radar-precipitation`
- **Documentation**: [https://opendatadocs.meteoswiss.ch/](https://opendatadocs.meteoswiss.ch/)
- **Authentication**: None.
- **Available Fields**: `item_id`, `bbox`, `datetime`, `assets` (HDF5 scans, quicklooks), `status`.
- **Update Frequency**: Scans generated every 5 minutes; STAC bundles published periodically.
- **Code Usage**:
  ```python
  from crisis_data.meteoswiss_radar import get_precipitation_radar
  radar = get_precipitation_radar(limit=3)
  ```
- **Test Result & Status**: **`WORKING`** (Retrieved latest STAC item with 864 HDF5 scans covering Swiss territory).

---

### 7. OpenStreetMap Overpass (Infrastructure)

- **Purpose**: Identification of emergency infrastructure within flood impact zones (hospitals, fire stations, bridges, emergency access points).
- **API Endpoint**: `https://overpass-api.de/api/interpreter` (with automatic fallback to `kumi.systems` and `private.coffee` mirrors).
- **Documentation**: [https://wiki.openstreetmap.org/wiki/Overpass_API](https://wiki.openstreetmap.org/wiki/Overpass_API)
- **Authentication**: None.
- **Available Fields**: `id`, `name`, `category` (hospital, fire_station, bridge), `location` (lat/lon), `tags`.
- **Update Frequency**: Continuously updated live OpenStreetMap database.
- **Code Usage**:
  ```python
  from crisis_data.osm_infrastructure import get_nearby_infrastructure
  infra = get_nearby_infrastructure(latitude=47.3769, longitude=8.5417, radius_km=2.5)
  ```
- **Test Result & Status**: **`WORKING`** (Retrieved 40 critical assets: USZ, Kinderspital, Neugasse Fire Station, Quaibrücke, etc.).

---

### 8. ASTRA Road Traffic (opentransportdata.swiss)

- **Purpose**: Real-time traffic disruptions, closures, and congestion warnings across Swiss national motorways (A1, A3, A4) affecting evacuation and dispatch routes.
- **API Endpoint**: `https://api.opentransportdata.swiss/TDP/Traffic_Data/DATEXII/situation`
- **Documentation**: [https://opentransportdata.swiss/en/road-traffic/](https://opentransportdata.swiss/en/road-traffic/)
- **Authentication**: **Requires API Key** (`OTD_API_KEY` in `.env` or passed via `Authorization: <KEY>`). Register for a free API token at [https://opentransportdata.swiss/en/register/](https://opentransportdata.swiss/en/register/).
- **Available Fields**: `incident_id`, `road`, `incident_type`, `description`, `location`, `is_closed`, `delay_minutes`, `updated_at`.
- **Update Frequency**: Continuous (DATEX II standard).
- **Code Usage**:
  ```python
  from crisis_data.astra_traffic import get_traffic_incidents
  incidents = get_traffic_incidents(road_filter="A1")
  ```
- **Test Result & Status**: **`NEEDS API KEY`** (Connectivity verified; returns graceful simulated fallback incident for emergency pipeline stability until key is provided).

---

### 9. Swiss Flood Hazard Maps (BAFU Aquaprotect)

- **Purpose**: Evaluates whether specific coordinates or infrastructure facilities fall directly inside official federal flood hazard inundation zones (return periods of 50, 100, 250, or 500 years).
- **API Endpoint**: `https://wms.geo.admin.ch/` (WMS 1.3.0 `GetFeatureInfo` on `ch.bafu.aquaprotect_100`)
- **Documentation**: [https://docs.geo.admin.ch/](https://docs.geo.admin.ch/)
- **Authentication**: None.
- **Available Fields**: `is_in_flood_zone` (bool), `risk_level` (HIGH, MEDIUM, LOW, NONE), `layer_name`, `geoportal_url`, `wms_overlay_url`.
- **Update Frequency**: Static federal hazard model (BAFU / FOEN Aquaprotect).
- **Code Usage**:
  ```python
  from crisis_data.flood_hazard import check_flood_hazard
  hazard = check_flood_hazard(latitude=47.3769, longitude=8.5417, return_period=100)
  ```
- **Test Result & Status**: **`WORKING`** (Coordinate evaluated in 0.05s; correctly produced risk assessment, LV95 projection, and Geoportal map preset links).

---

### 10. Official Swiss Hazard Warnings (natural-hazards.ch)

- **Purpose**: Ingestion of the official federal natural hazard alerting feed (Common Alerting Protocol / MeteoSwiss backend) covering flood, storm, rain, snow, and fire danger levels (1 to 5).
- **API Endpoint**: `https://app-prod-ws.meteoswiss-app.ch/v1/plzDetail?plz={plz}`
- **Documentation**: [https://www.natural-hazards.ch/](https://www.natural-hazards.ch/)
- **Authentication**: None.
- **Available Fields**: `plz`, `max_warning_level` (1=None, 2=Moderate, 3=Significant, 4=Severe, 5=Very Severe), `warnings` (hazard_type, description, valid_from, direct_url), `portal_url`.
- **Update Frequency**: Updated immediately upon official federal alert issuance.
- **Code Usage**:
  ```python
  from crisis_data.hazard_warnings import get_warning_summary, get_hazard_warnings
  summary = get_warning_summary(plz="800100")  # Zurich Center
  ```
- **Test Result & Status**: **`WORKING`** (Retrieved active federal warnings feed in 0.12s; parsed max danger level and official advice).

---

### 11. ETH Swiss Seismological Service (SED)

- **Purpose**: Real-time earthquake catalog covering Switzerland and surrounding alpine regions (magnitude, epicenter coordinates, depth, time).
- **API Endpoint**: `http://arclink.ethz.ch/fdsnws/event/1/query?format=text`
- **Documentation**: [https://www.seismo.ethz.ch/](https://www.seismo.ethz.ch/)
- **Authentication**: None (FDSN open service).
- **Available Fields**: `event_id`, `time`, `latitude`, `longitude`, `depth_km`, `magnitude`, `location_name`, `event_type`.
- **Update Frequency**: Real-time (automated detections posted within seconds).
- **Code Usage**:
  ```python
  from crisis_data.sed_earthquakes import get_earthquake_summary, get_recent_earthquakes
  summary = get_earthquake_summary()
  ```
- **Test Result & Status**: **`WORKING`** (Retrieved 10 recent seismic events across Switzerland; parsed magnitudes and epicenters).

---

### 12. Swiss Population and Building Data (BFS)

- **Purpose**: Demographic density (STATPOP) and building registry (GWR) exposure estimation to identify vulnerable structures, pre-1950 buildings, and exposed population counts in flood zones.
- **API Endpoint**: `https://api3.geo.admin.ch/rest/services/all/MapServer/find?layer=ch.bfs.gebaeude_wohnungs_register`
- **Documentation**: [https://www.bfs.admin.ch/](https://www.bfs.admin.ch/)
- **Authentication**: None.
- **Available Fields**: `egid`, `address`, `construction_year`, `floors`, `municipality`, `population_density_per_km2`, `average_building_floors`, `historic_buildings_pre_1950`.
- **Update Frequency**: Annually updated federal statistical registers.
- **Code Usage**:
  ```python
  from crisis_data.bfs_population import get_population_exposure_metrics, get_building_exposure
  metrics = get_population_exposure_metrics(postal_code=8001)
  ```
- **Test Result & Status**: **`WORKING`** (Queried 50 sample buildings for Zurich 8001; computed demographic density and historic building ratios).

---

## 3. Health Status Matrix

The following live audit status was produced by executing `python test_integrations.py`:

|  #  | Source                               | Auth required | Connectivity | Real data retrieved | Freshness                               |      Status       |
| :-: | :----------------------------------- | :-----------: | :----------: | :-----------------: | :-------------------------------------- | :---------------: |
|  1  | **Open-Meteo Weather**               |      No       | ✓ Connected  |        ✓ Yes        | Live (15-min intervals)                 |    **WORKING**    |
|  2  | **BAFU / FOEN Hydrology**            |      No       | ✓ Connected  |        ✓ Yes        | Live (10-min intervals)                 |    **WORKING**    |
|  3  | **Windy Webcams V3**                 |      Yes      | ✓ Connected  |        ✓ Yes        | Near real-time (15-min to 1-hr updates) |    **WORKING**    |
|  4  | **swisstopo Geodata**                |      No       | ✓ Connected  |        ✓ Yes        | Static DEM / Official Cartography       |    **WORKING**    |
|  5  | **MeteoSwiss Weather Stations**      |      No       | ✓ Connected  |        ✓ Yes        | Observed at 10.10.2026 11:40            |    **WORKING**    |
|  6  | **MeteoSwiss Precipitation Radar**   |      No       | ✓ Connected  |        ✓ Yes        | Latest update: 2026-10-04T05:04:53Z     |    **WORKING**    |
|  7  | **OpenStreetMap Overpass**           |      No       | ✓ Connected  |        ✓ Yes        | Live OSM Database                       |    **WORKING**    |
|  8  | **ASTRA Road Traffic**               |      Yes      | ✓ Connected  |        ✕ No         | N/A (Key required)                      | **NEEDS API KEY** |
|  9  | **Swiss Flood Hazard Maps**          |      No       | ✓ Connected  |        ✓ Yes        | Official BAFU Model (geo.admin.ch WMS)  |    **WORKING**    |
| 10  | **Official Swiss Hazard Warnings**   |      No       | ✓ Connected  |        ✓ Yes        | Live Federal Alerting Feed              |    **WORKING**    |
| 11  | **ETH Swiss Seismological Service**  |      No       | ✓ Connected  |        ✓ Yes        | Latest: 2026-10-09T03:03:52Z            |    **WORKING**    |
| 12  | **Swiss Population & Building Data** |      No       | ✓ Connected  |        ✓ Yes        | Federal GWR & STATPOP Register          |    **WORKING**    |

### Status Breakdown:

- **WORKING**: **11**
- **NEEDS API KEY**: **1** (ASTRA Road Traffic — opentransportdata.swiss token required)
- **PARTIALLY WORKING**: **0**
- **BLOCKED**: **0**
- **Total Working / Operational Integrations**: **11 / 12** (100% of non-restricted sources operational)

---

## 4. Running the Integration Smoke Tests

Run the complete 12-source automated diagnostic suite with:

```bash
# Activate virtual environment
source .venv/bin/activate

# Execute smoke test suite
python test_integrations.py
```

The script will:

1. Connect to each of the 12 endpoints sequentially.
2. Verify HTTP responses, validate JSON/XML parsing, check coordinate projections, and assert schema integrity.
3. Query the `HealthMonitor` across all 12 services and output the formatted GitHub Markdown health table.
4. Exit with return code `0` when tests succeed.

---

## 5. Exposing Data to the Gemini Reasoning Agent

All data sources are exported as standalone, typed functions in [`crisis_data/agent_tools.py`](../crisis_data/agent_tools.py), ready for registration in Google Gemini Tool Declarations (`google.genai.types.Tool`):

```python
from google import genai
from google.genai import types
from crisis_data.agent_tools import (
    get_weather,
    get_river_stations,
    get_river_measurements,
    get_nearby_webcams,
    get_webcam_image,
    get_weather_stations,
    get_precipitation_radar,
    get_nearby_infrastructure,
    get_traffic_incidents,
    check_flood_hazard,
    get_hazard_warnings,
    get_warning_summary,
    get_recent_earthquakes,
    get_earthquake_summary,
    get_building_exposure,
    get_population_exposure_metrics,
    get_data_source_health,
)

# Register tools with Gemini client
client = genai.Client()
response = client.models.generate_content(
    model="gemini-2.5-flash",
    contents="Assess the flood risk for Zurich Central and check if nearby bridges are endangered.",
    config=types.GenerateContentConfig(
        tools=[
            get_weather,
            get_river_measurements,
            check_flood_hazard,
            get_nearby_infrastructure,
            get_traffic_incidents,
            get_hazard_warnings,
            get_nearby_webcams,
        ]
    ),
)
```
