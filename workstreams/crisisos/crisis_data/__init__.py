"""
CrisisOS Switzerland — Data Integration Package.

Provides autonomous, multimodal disaster intelligence integrations connecting
real Swiss hydrological, meteorological, elevation, radar, visual, and infrastructure data
to the Google Gemini reasoning agent.
"""

from crisis_data.config import Config, get_config
from crisis_data.logger import logger, log_function_call, log_genai_call
from crisis_data.models import (
    NormalizedObservation,
    CameraMetadata,
    InfrastructureItem,
    DataSourceHealth,
    GeoLocation,
    TrafficIncident,
    FloodHazardInfo,
    HazardWarning,
    EarthquakeEvent,
    BuildingExposureInfo,
)
from crisis_data.agent_tools import (
    get_weather,
    get_river_stations,
    get_river_measurements,
    get_nearby_webcams,
    get_webcam_image,
    get_elevation,
    get_weather_stations,
    get_meteoswiss_observation,
    get_precipitation_radar,
    get_nearby_infrastructure,
    get_data_source_health,
    get_traffic_incidents,
    check_flood_hazard,
    get_hazard_warnings,
    get_warning_summary,
    get_recent_earthquakes,
    get_earthquake_summary,
    get_building_exposure,
    get_population_exposure_metrics,
)

__all__ = [
    "Config",
    "get_config",
    "logger",
    "log_function_call",
    "log_genai_call",
    "NormalizedObservation",
    "CameraMetadata",
    "InfrastructureItem",
    "DataSourceHealth",
    "GeoLocation",
    "TrafficIncident",
    "FloodHazardInfo",
    "HazardWarning",
    "EarthquakeEvent",
    "BuildingExposureInfo",
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
