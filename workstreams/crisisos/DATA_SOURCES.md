# CrisisOS Switzerland — Data Sources & Integration Guide

This document provides a comprehensive reference for all external data sources integrated into **CrisisOS Switzerland**, with a specific focus on flood intelligence and emergency monitoring in Zurich (Limmat and Sihl rivers).

---

## Summary Matrix

| Data Source          | Priority | Provider                | Authentication              | Frequency / Freshness         | Endpoint / Protocol   | Primary Python Module                                                 |
| :------------------- | :------: | :---------------------- | :-------------------------- | :---------------------------- | :-------------------- | :-------------------------------------------------------------------- |
| **Open-Meteo**       |    P1    | Open-Meteo              | None (Public)               | 15-min / Hourly forecast      | REST JSON             | [`crisis_data.open_meteo`](crisis_data/open_meteo.py)                 |
| **BAFU / FOEN**      |    P2    | Swiss FOEN / BAFU       | None (Public)               | 10-min live stream            | GraphQL               | [`crisis_data.bafu_hydro`](crisis_data/bafu_hydro.py)                 |
| **Windy Webcams**    |    P3    | Windy.com               | API Key (`x-windy-api-key`) | 15–30 min images              | REST JSON / Image     | [`crisis_data.windy_webcams`](crisis_data/windy_webcams.py)           |
| **swisstopo**        |    P4    | Federal Geo-Information | None (Public)               | Static / Cartographic         | REST GeoJSON & DEM    | [`crisis_data.swisstopo`](crisis_data/swisstopo.py)                   |
| **MeteoSwiss SMN**   |    P5    | MeteoSwiss              | None (Public OGD)           | 10-minute ground observations | STAC API + CSV stream | [`crisis_data.meteoswiss_smn`](crisis_data/meteoswiss_smn.py)         |
| **MeteoSwiss Radar** |    P6    | MeteoSwiss              | None (Public OGD)           | 5-minute radar composites     | STAC Catalog (HDF5)   | [`crisis_data.meteoswiss_radar`](crisis_data/meteoswiss_radar.py)     |
| **OSM Overpass**     |    P7    | OpenStreetMap           | None (Public, Rate-limited) | Dynamic OSM DB                | Overpass QL / JSON    | [`crisis_data.osm_infrastructure`](crisis_data/osm_infrastructure.py) |

---

## 1. Open-Meteo Weather API (Priority 1)

- **Documentation**: [https://open-meteo.com/en/docs](https://open-meteo.com/en/docs)
- **Endpoint**: `https://api.open-meteo.com/v1/forecast`
- **Default Zurich Coordinates**: Latitude `47.3769`, Longitude `8.5417`
- **Authentication**: None required for non-commercial open data usage.
- **Retrieved Parameters**:
  - Current conditions: `temperature_2m`, `relative_humidity_2m`, `precipitation`, `rain`, `weather_code`, `wind_speed_10m`, `wind_direction_10m`, `wind_gusts_10m`.
  - Forecast & accumulations: 24h precipitation sum, 24h rain sum, 48-hour hourly outlook.
- **Normalized Model**: [`NormalizedObservation`](crisis_data/models.py) with source `"open_meteo"`.
- **Gemini Tool**: [`get_weather(latitude, longitude)`](crisis_data/agent_tools.py).
- **Validation & Error Handling**: Gracefully returns error status in JSON structure if network fails; parameters outside Swiss boundaries validate coordinates.

---

## 2. BAFU / FOEN Swiss Hydrological Data (Priority 2)

- **Documentation**: [https://data.bafu.admin.ch/en/](https://data.bafu.admin.ch/en/)
- **GraphQL Endpoint**: `https://data.bafu.admin.ch/api`
- **Authentication**: None required for the public GraphQL endpoint.
- **Key Hydrological Stations (Zurich Focus)**:
  - **Station 2176**: _Zürich, Sihlhölzli_ on the **Sihl** (Lat: 47.3688, Lon: 8.5276).
  - **Station 2099**: _Zürich, Unterhard_ on the **Limmat** (Lat: 47.3917, Lon: 8.5085).
  - **Station 2209**: _Zürich, Kornhausbrücke / Zürichsee_.
- **Retrieved Measurements**:
  - `W`: River water level in meters above sea level (`m a.s.l.`).
  - `Q`: River discharge in cubic meters per second (`m³/s`).
  - `WT`: Water temperature in degrees Celsius (`°C`).
- **GraphQL Schema Structure**:
  ```graphql
  query GetLiveStationData {
    water {
      observations {
        data_live(where: { stationNo: { _eq: "2176" } }) {
          stationNo
          parameterName
          timestamp
          value
          releaseStatus
        }
      }
    }
  }
  ```
- **Gemini Tools**:
  - [`get_river_stations()`](crisis_data/agent_tools.py)
  - [`get_river_measurements(station_no)`](crisis_data/agent_tools.py)
- **Data Policy**: Zero synthetic interpolation. Only real measurements from BAFU are presented.

---

## 3. Windy Webcams API V3 (Priority 3)

- **Documentation**: [https://api.windy.com/webcams/docs](https://api.windy.com/webcams/docs)
- **Endpoint**: `https://api.windy.com/webcams/api/v3/webcams`
- **Authentication**: Requires header `x-windy-api-key: <KEY>`. Set via `WINDY_API_KEY` in `.env`.
- **How to Obtain Key**:
  1. Register at [https://api.windy.com/](https://api.windy.com/).
  2. Create a project and activate the **Webcams API V3** service.
  3. Copy the API token and add to `.env`: `WINDY_API_KEY=your_key`.
- **Retrieved Information**:
  - Camera ID, title, status (`active`/`inactive`), coordinates (WGS84).
  - Image URLs (`current`, `daylight`), capture timestamps, tokenized lifetime.
- **Multimodal Image Retrieval**:
  - [`get_webcam_image(camera_id, image_url)`](crisis_data/agent_tools.py) downloads and base64-encodes actual JPEG imagery for direct consumption by Google Gemini 2.5 Flash / Pro visual reasoning.
- **Graceful Degradation**:
  - When `WINDY_API_KEY` is not present, the client returns fallback camera records with `is_simulated=True` and status `"NEEDS API KEY (Graceful Fallback)"`, preventing pipeline crashes during offline testing.

---

## 4. swisstopo / Swiss Federal Geodata (Priority 4)

- **Documentation**: [https://docs.geo.admin.ch/](https://docs.geo.admin.ch/)
- **Endpoints**:
  - **Digital Elevation Model (DEM)**: `https://api3.geo.admin.ch/rest/services/height`
  - **Geoportal Viewer**: `https://map.geo.admin.ch/`
- **Authentication**: None required for open geodata services.
- **Coordinate Systems**:
  - **WGS84 (EPSG:4326)**: Standard GPS coordinates used by Open-Meteo, Windy, and Gemini (`[lat, lon]`).
  - **LV95 (EPSG:2056)**: Swiss national coordinate system in meters (`[East: 2'600'000, North: 1'200'000]`).
  - Implemented closed-form analytical transformations between WGS84 and LV95 in [`swisstopo.py`](crisis_data/swisstopo.py) matching official swisstopo formulas to eliminate network round-trips.
- **Capabilities Exposed**:
  - Precise ground elevation lookup in meters a.s.l. (e.g., Zurich center = `408.4 m`).
  - Interactive map link generation with layer overlays (e.g., flood hazard layer `ch.bafu.gefahren-hochwasser`).

---

## 5. MeteoSwiss Weather Stations — SwissMetNet (Priority 5)

- **Documentation**: [https://opendatadocs.meteoswiss.ch/a-data-groundbased/a1-automatic-weather-stations](https://opendatadocs.meteoswiss.ch/a-data-groundbased/a1-automatic-weather-stations)
- **STAC Endpoint**: `https://data.geo.admin.ch/api/stac/v1/collections/ch.meteoschweiz.ogd-smn`
- **Data Stream**: Live 10-minute automated station observations published in CSV format.
- **Zurich Region Stations**:
  - `sma`: Zürich / Fluntern (Lat: 47.378, Lon: 8.566, Elev: 556m) — Official urban reference.
  - `reh`: Zürich / Affoltern (Lat: 47.428, Lon: 8.518, Elev: 443m).
  - `klo`: Zürich / Kloten Airport (Lat: 47.480, Lon: 8.536, Elev: 428m).
- **Retrieved Parameters**:
  - Air temperature (`tre200s0`, °C)
  - Relative humidity (`ure200s0`, %)
  - 10-minute precipitation sum (`rre150z0`, mm)
  - Mean wind speed (`fkl010z0`, m/s) and gust peak (`fkl010z1`, m/s)
  - Direct solar radiation (`gre000z0`, W/m²)
- **Freshness**: Updated every 10 minutes. Includes exact measurement timestamp.

---

## 6. MeteoSwiss Precipitation Radar (Priority 6)

- **Documentation**: [https://opendatadocs.meteoswiss.ch/d-radar-data/d1-precipitation-radar-products](https://opendatadocs.meteoswiss.ch/d-radar-data/d1-precipitation-radar-products)
- **STAC Endpoint**: `https://data.geo.admin.ch/api/stac/v1/collections/ch.meteoschweiz.ogd-radar-precip`
- **Data Format**: 5-minute radar composites stored as HDF5 (`application/x-hdf5`).
- **Implementation Strategy**:
  - Queries the GeoAdmin STAC collection for latest available radar composite items over Switzerland.
  - Extracts spatial coverage bounding boxes (`[5.96, 45.82, 10.49, 47.81]`), scan counts (864 scans/day), and asset download URLs.
  - Exposes valid asset metadata for Gemini agent inspection without bloating container requirements with heavy C-based HDF5/GDAL binaries during the rapid hackathon sprint.

---

## 7. OpenStreetMap / Overpass Infrastructure (Priority 7)

- **Documentation**: [https://wiki.openstreetmap.org/wiki/Overpass_API](https://wiki.openstreetmap.org/wiki/Overpass_API)
- **Endpoint**: `https://overpass-api.de/api/interpreter`
- **Authentication**: None. Requires valid custom `User-Agent` header (`CrisisOS-Zurich/1.0`).
- **Target Emergency Infrastructure Categories**:
  - `hospital` (`amenity=hospital`)
  - `fire_station` (`amenity=fire_station`)
  - `bridge` (`man_made=bridge`)
  - `school` (`amenity=school`)
  - `police` (`amenity=police`)
- **Optimization & Rate Limiting**:
  - Geo-bounded queries restricted to radius around Zurich flood zones.
  - Thread-safe in-memory cache with 15-minute TTL to respect OSM server limits.
  - Output features normalized into standardized `InfrastructureItem` dictionaries.

---

## 8. Data Health Monitoring & Verification

CrisisOS includes a centralized health inspector module: [`crisis_data.health`](crisis_data/health.py).

To execute the automated smoke test across all 7 sources:

```bash
# Activate virtual environment
source .venv/bin/activate

# Run end-to-end integration test
python3 test_integrations.py
```

### Live Test Results (October 10, 2026)

| Source                         | Auth required | Connectivity | Real data retrieved | Freshness                               |   Status    |
| :----------------------------- | :-----------: | :----------: | :-----------------: | :-------------------------------------- | :---------: |
| Open-Meteo Weather             |      No       | ✓ Connected  |        ✓ Yes        | Live (15-min intervals)                 | **WORKING** |
| BAFU / FOEN Hydrology          |      No       | ✓ Connected  |        ✓ Yes        | Live (10-min intervals)                 | **WORKING** |
| Windy Webcams V3               |      Yes      | ✓ Connected  |        ✓ Yes        | Near real-time (15-min to 1-hr updates) | **WORKING** |
| swisstopo Geodata              |      No       | ✓ Connected  |        ✓ Yes        | Static DEM / Official Cartography       | **WORKING** |
| MeteoSwiss Weather Stations    |      No       | ✓ Connected  |        ✓ Yes        | Observed at 10.10.2026 10:40            | **WORKING** |
| MeteoSwiss Precipitation Radar |      No       | ✓ Connected  |        ✓ Yes        | Latest update: 2026-10-04T05:04:53Z     | **WORKING** |
| OpenStreetMap Overpass         |      No       | ✓ Connected  |        ✓ Yes        | Live OSM Database                       | **WORKING** |
