"""
Centralized Configuration Module for CrisisOS Switzerland Data Integration.

This module consolidates all application configurations, endpoint definitions,
default coordinates, timeouts, and environment variable loaders in one centralized location.
By gathering all settings here, the application avoids hardcoded constants across different
modules and enables uniform environment variable management.

Use Cases:
1. Loading and validating environment variables (e.g., API keys for Windy Webcams, Gemini API).
2. Supplying default coordinates, bounding boxes, and radii for Zurich and Swiss water bodies (Limmat, Sihl).
3. Defining standard HTTP timeouts, user agents, and retry thresholds across all integration clients.
4. Centralizing model names and GenAI configurations for the Gemini reasoning agent.
"""

import os
from typing import Optional
from dotenv import load_dotenv

# Load local .env file if available
load_dotenv()


class Config:
    """Central configuration class holding all constants, endpoints, and credentials."""

    # --------------------------------------------------------------------------
    # Geographic Focus: Zurich & Switzerland
    # --------------------------------------------------------------------------
    ZURICH_LAT: float = 47.3769
    ZURICH_LON: float = 8.5417
    DEFAULT_RADIUS_KM: float = 15.0

    # Bounding box for Zurich metro area [south_lat, west_lon, north_lat, east_lon]
    ZURICH_BBOX: dict[str, float] = {
        "min_lat": 47.3200,
        "min_lon": 8.4500,
        "max_lat": 47.4500,
        "max_lon": 8.6200,
    }

    # --------------------------------------------------------------------------
    # Priority 1: Open-Meteo Weather API
    # --------------------------------------------------------------------------
    OPEN_METEO_BASE_URL: str = "https://api.open-meteo.com/v1/forecast"
    OPEN_METEO_TIMEOUT_SECONDS: int = 10

    # --------------------------------------------------------------------------
    # Priority 2: BAFU / FOEN Hydrology GraphQL
    # --------------------------------------------------------------------------
    BAFU_GRAPHQL_URL: str = "https://data.bafu.admin.ch/api"
    BAFU_TIMEOUT_SECONDS: int = 15
    # Key stations near Zurich:
    # 2176: Zürich, Sihlhölzli (River Sihl)
    # 2099: Zürich, Unterhard (River Limmat)
    # 2209: Zürich (Zürichsee)
    # 2243: Baden, Limmatpromenade (River Limmat downstream)
    BAFU_PRIMARY_ZURICH_STATIONS: list[str] = ["2176", "2099", "2209", "2243"]

    # --------------------------------------------------------------------------
    # Priority 3: Windy Webcams API V3
    # --------------------------------------------------------------------------
    WINDY_WEBCAMS_BASE_URL: str = "https://api.windy.com/webcams/api/v3/webcams"
    WINDY_TIMEOUT_SECONDS: int = 10
    WINDY_API_KEY: Optional[str] = os.getenv("WINDY_API_KEY") or os.getenv("WINDY_WEBCAM_API_KEY") or os.getenv("WINDY_WEBCAMS_API_KEY")

    # --------------------------------------------------------------------------
    # Priority 4: swisstopo / Swiss Federal Geodata
    # --------------------------------------------------------------------------
    SWISSTOPO_STAC_BASE_URL: str = "https://data.geo.admin.ch/api/stac/v1"
    SWISSTOPO_REST_BASE_URL: str = "https://api3.geo.admin.ch/rest/services"
    SWISSTOPO_HEIGHT_URL: str = "https://api3.geo.admin.ch/rest/services/height"
    SWISSTOPO_GEODESY_URL: str = "https://geodesy.geo.admin.ch/reframe"
    SWISSTOPO_TIMEOUT_SECONDS: int = 10

    # --------------------------------------------------------------------------
    # Priority 5: MeteoSwiss Weather Stations (SwissMetNet)
    # --------------------------------------------------------------------------
    METEOSWISS_SMN_STAC_URL: str = "https://data.geo.admin.ch/api/stac/v1/collections/ch.meteoschweiz.ogd-smn"
    METEOSWISS_SMN_ASSET_BASE: str = "https://data.geo.admin.ch/ch.meteoschweiz.ogd-smn"
    METEOSWISS_SMN_TIMEOUT_SECONDS: int = 15
    METEOSWISS_DEFAULT_STATION: str = "sma"  # Zürich / Fluntern

    # --------------------------------------------------------------------------
    # Priority 6: MeteoSwiss Precipitation Radar
    # --------------------------------------------------------------------------
    METEOSWISS_RADAR_STAC_URL: str = "https://data.geo.admin.ch/api/stac/v1/collections/ch.meteoschweiz.ogd-radar-precip"
    METEOSWISS_RADAR_TIMEOUT_SECONDS: int = 15

    # --------------------------------------------------------------------------
    # Priority 7: OpenStreetMap / Overpass API
    # --------------------------------------------------------------------------
    OVERPASS_API_URL: str = "https://overpass-api.de/api/interpreter"
    OVERPASS_USER_AGENT: str = "CrisisOS-Zurich/1.0 (hackathon-emergency-agent; https://github.com/ixsanpe/hackathon-tech-europe)"
    OVERPASS_TIMEOUT_SECONDS: int = 25

    # --------------------------------------------------------------------------
    # Gemini / GenAI Configuration
    # --------------------------------------------------------------------------
    GEMINI_API_KEY: Optional[str] = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    GEMINI_DEFAULT_MODEL: str = "gemini-2.5-flash"
    GEMINI_VISION_MODEL: str = "gemini-2.5-flash"
    GEMINI_REASONING_MODEL: str = "gemini-2.5-pro"

    # --------------------------------------------------------------------------
    # Priority 8: ASTRA Road Traffic (opentransportdata.swiss)
    # --------------------------------------------------------------------------
    ASTRA_TRAFFIC_URL: str = "https://api.opentransportdata.swiss/TDP/Soap_Datex2/TrafficSituations/Pull"
    ASTRA_TIMEOUT_SECONDS: int = 15
    OTD_API_KEY: Optional[str] = os.getenv("OTD_API_KEY") or os.getenv("ASTRA_API_KEY")

    # --------------------------------------------------------------------------
    # Priority 9: Swiss Flood Hazard Maps (BAFU Aquaprotect)
    # --------------------------------------------------------------------------
    BAFU_WMS_URL: str = "https://wms.geo.admin.ch/"
    BAFU_AQUAPROTECT_LAYER_100: str = "ch.bafu.aquaprotect_100"
    BAFU_AQUAPROTECT_LAYER_50: str = "ch.bafu.aquaprotect_050"
    BAFU_AQUAPROTECT_LAYER_250: str = "ch.bafu.aquaprotect_250"
    BAFU_AQUAPROTECT_LAYER_500: str = "ch.bafu.aquaprotect_500"
    FLOOD_HAZARD_TIMEOUT_SECONDS: int = 10

    # --------------------------------------------------------------------------
    # Priority 10: Official Swiss Hazard Warnings (natural-hazards.ch backend)
    # --------------------------------------------------------------------------
    NATURAL_HAZARDS_BASE_URL: str = "https://app-prod-ws.meteoswiss-app.ch/v1"
    NATURAL_HAZARDS_PLZ_ENDPOINT: str = "https://app-prod-ws.meteoswiss-app.ch/v1/plzDetail"
    NATURAL_HAZARDS_TIMEOUT_SECONDS: int = 10
    DEFAULT_ZURICH_PLZ: str = "800100"

    # --------------------------------------------------------------------------
    # Priority 11: ETH Swiss Seismological Service (SED)
    # --------------------------------------------------------------------------
    SED_FDSN_URL: str = "http://arclink.ethz.ch/fdsnws/event/1/query"
    SED_TIMEOUT_SECONDS: int = 10
    SED_DEFAULT_MIN_MAGNITUDE: float = 0.5

    # --------------------------------------------------------------------------
    # Priority 12: Swiss Population and Building Exposure (BFS)
    # --------------------------------------------------------------------------
    BFS_GWR_SEARCH_URL: str = "https://api3.geo.admin.ch/rest/services/all/MapServer/find"
    BFS_GWR_LAYER: str = "ch.bfs.gebaeude_wohnungs_register"
    BFS_TIMEOUT_SECONDS: int = 15
    BFS_ZURICH_MUNICIPALITY_ID: int = 261
    BFS_ZURICH_POPULATION_ESTIMATE: int = 447000
    BFS_ZURICH_AREA_KM2: float = 87.93
    BFS_ZURICH_DENSITY_PER_KM2: float = 5084.0

    # --------------------------------------------------------------------------
    # General HTTP & Cache Settings
    # --------------------------------------------------------------------------
    HTTP_MAX_RETRIES: int = 2
    HTTP_BACKOFF_FACTOR: float = 0.5
    CACHE_EXPIRATION_SECONDS: int = 180  # 3 minutes default memory cache


def get_config() -> type[Config]:
    """
    Return the global Config class.

    Returns:
        The Config class containing all environment and operational constants.
    """
    return Config
