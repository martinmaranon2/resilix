"""
Normalized Data Models for CrisisOS Switzerland.

This module defines standard data structures and schemas used across all CrisisOS data integrations.
Normalizing incoming data from disparate providers (Open-Meteo, BAFU GraphQL, swisstopo, MeteoSwiss,
Windy, and OpenStreetMap) into a uniform schema allows the Gemini reasoning agent and downstream
services to process environmental, hydrological, and infrastructure information seamlessly.

Use Cases:
1. Normalizing river gauge observations (water level, discharge) into standard SI/metric units.
2. Structuring weather and precipitation readings with explicit timestamps and freshness indicators.
3. Modeling public camera feeds (images, coordinates, update timestamps) for multimodal Gemini ingestion.
4. Encapsulating infrastructure features (hospitals, fire stations, bridges) around Zurich.
5. Standardizing health check reporting across all integrated data providers.
"""

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional


def current_utc_iso() -> str:
    """
    Generate the current UTC timestamp formatted as an ISO-8601 string.

    Returns:
        ISO-8601 formatted timestamp in UTC.
    """
    return datetime.now(timezone.utc).isoformat()


@dataclass
class GeoLocation:
    """Geographic point representation in standard WGS84 coordinates."""
    latitude: float
    longitude: float
    elevation_m: Optional[float] = None

    def to_dict(self) -> dict[str, Any]:
        """Convert location to a dictionary."""
        d = {"latitude": self.latitude, "longitude": self.longitude}
        if self.elevation_m is not None:
            d["elevation_m"] = self.elevation_m
        return d


@dataclass
class NormalizedObservation:
    """
    Normalized environmental or hydrological observation record.

    Follows the CrisisOS standard schema required for Gemini decision-making.
    """
    source: str
    type: str
    station_id: str
    location: Optional[dict[str, Any]]
    measurement: dict[str, Any]
    observed_at: str
    retrieved_at: str = field(default_factory=current_utc_iso)
    is_simulated: bool = False
    quality: str = "nominal"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert the normalized observation to a clean dictionary."""
        return asdict(self)


@dataclass
class CameraMetadata:
    """Metadata describing a public monitoring webcam."""
    camera_id: str
    title: str
    location: Optional[dict[str, Any]]
    image_url: Optional[str]
    preview_url: Optional[str]
    updated_at: Optional[str]
    status: str
    source: str = "Windy"
    is_simulated: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convert camera metadata to dictionary."""
        return asdict(self)


@dataclass
class InfrastructureItem:
    """Critical or emergency infrastructure feature extracted from OpenStreetMap."""
    id: str
    name: str
    category: str  # e.g., 'hospital', 'fire_station', 'bridge'
    location: dict[str, float]
    tags: dict[str, str] = field(default_factory=dict)
    source: str = "OpenStreetMap"
    is_simulated: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convert infrastructure item to dictionary."""
        return asdict(self)


@dataclass
class DataSourceHealth:
    """Health check outcome for an external data source."""
    source: str
    auth_required: bool
    connectivity: bool
    real_data_retrieved: bool
    freshness: str
    status: str  # 'WORKING', 'PARTIALLY WORKING', 'NEEDS API KEY', 'BLOCKED', 'NOT IMPLEMENTED'
    details: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert health record to dictionary."""
        return asdict(self)


@dataclass
class TrafficIncident:
    """Road traffic incident, road closure, or obstruction from ASTRA / TDP."""
    incident_id: str
    road_number: str
    direction: Optional[str]
    incident_type: str  # e.g., 'roadworks', 'closure', 'accident', 'congestion'
    description: str
    location: Optional[dict[str, Any]]
    is_closed: bool
    delay_minutes: Optional[int]
    updated_at: str
    source: str = "ASTRA_FEDRO"
    is_simulated: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convert incident to dictionary."""
        return asdict(self)


@dataclass
class FloodHazardInfo:
    """Swiss flood hazard zoning information (BAFU Aquaprotect)."""
    latitude: float
    longitude: float
    lv95_east: float
    lv95_north: float
    is_in_flood_zone: bool
    return_period_years: int  # 50, 100, 250, 500
    risk_level: str  # 'HIGH', 'MEDIUM', 'LOW', 'NONE', 'UNKNOWN'
    layer_name: str
    geoportal_url: str
    wms_overlay_url: str
    source: str = "BAFU_Aquaprotect"
    data_available: bool = True
    status: str = "NOMINAL"

    def to_dict(self) -> dict[str, Any]:
        """Convert flood hazard info to dictionary."""
        return asdict(self)


@dataclass
class HazardWarning:
    """Official Swiss natural hazard warning (flood, storm, rain, fire, etc.)."""
    warning_id: str
    warn_type: int
    warn_type_name: str  # e.g., 'Flood', 'Thunderstorm', 'Forest Fire', 'Rain'
    warn_level: int  # 1 (low) to 5 (extreme)
    region_id: int
    region_name: str
    description: str
    valid_from: str
    valid_to: Optional[str]
    direct_url: str
    source: str = "natural-hazards.ch"

    def to_dict(self) -> dict[str, Any]:
        """Convert warning to dictionary."""
        return asdict(self)


@dataclass
class EarthquakeEvent:
    """Seismic event record from ETH Swiss Seismological Service (SED)."""
    event_id: str
    timestamp: str
    latitude: float
    longitude: float
    depth_km: float
    magnitude: float
    magnitude_type: str
    location_name: str
    event_type: str  # e.g., 'earthquake', 'quarry blast', 'explosion'
    source: str = "SED_ETHZ"
    is_simulated: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convert earthquake event to dictionary."""
        return asdict(self)


@dataclass
class BuildingExposureInfo:
    """Building record and population exposure metric from BFS (GWR)."""
    egid: str
    street: str
    house_number: str
    postal_code: int
    municipality: str
    year_built: Optional[int]
    floors: Optional[int]
    area_m2: Optional[float]
    latitude: Optional[float]
    longitude: Optional[float]
    population_density_km2: float
    source: str = "BFS_GWR"
    is_simulated: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convert building exposure to dictionary."""
        return asdict(self)
