"""
Unified Gemini Agent Tooling Interface for CrisisOS Switzerland.

This module exposes the standardized tool signatures required by the main Google Gemini
reasoning and decision-making agent. These functions provide structured, normalized,
and error-handled environmental, hydrological, geographical, visual, and infrastructural data
without hardcoded business logic or simulated emergency dispatch actions.

Use Cases:
1. Tool calling by Gemini 2.5 Flash / Pro during incident triage and situational awareness.
2. Direct invocation by multimodal reasoning chains comparing visual camera evidence with sensor telemetry.
3. Health monitoring and automated fallback detection for commander voice queries (Gradium).
"""

from typing import Any, Optional

from crisis_data.config import Config
from crisis_data.logger import log_function_call
from crisis_data.open_meteo import get_weather
from crisis_data.bafu_hydro import get_river_stations, get_river_measurements
from crisis_data.windy_webcams import get_nearby_webcams, get_webcam_image
from crisis_data.swisstopo import get_elevation
from crisis_data.meteoswiss_smn import get_weather_stations, get_meteoswiss_observation
from crisis_data.meteoswiss_radar import get_precipitation_radar
from crisis_data.osm_infrastructure import get_nearby_infrastructure
from crisis_data.health import get_data_source_health
from crisis_data.astra_traffic import get_traffic_incidents
from crisis_data.flood_hazard import check_flood_hazard
from crisis_data.hazard_warnings import get_hazard_warnings, get_warning_summary
from crisis_data.sed_earthquakes import get_recent_earthquakes, get_earthquake_summary
from crisis_data.bfs_population import get_building_exposure, get_population_exposure_metrics

__all__ = [
    "get_weather",
    "get_river_stations",
    "get_river_measurements",
    "get_nearby_webcams",
    "get_webcam_image",
    "get_elevation",
    "get_weather_stations",
    "get_meteoswiss_observation",
    "get_precipitation_radar",
    "get_nearby_infrastructure",
    "get_data_source_health",
    "get_traffic_incidents",
    "check_flood_hazard",
    "get_hazard_warnings",
    "get_warning_summary",
    "get_recent_earthquakes",
    "get_earthquake_summary",
    "get_building_exposure",
    "get_population_exposure_metrics",
]
