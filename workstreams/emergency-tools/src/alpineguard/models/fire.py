"""
Forest fire types: hotspots, weather, sensor frames and spread forecasts.

Architecture
------------
The forest fire tools combine satellite hotspots, weather, drone and camera frames and
a simple spread model. These dataclasses carry that data between the simulated world,
the spread model and the tool results. Every record that comes from a scenario file has
``is_simulated`` set; computed forecasts carry the model name and its limits.

Use cases
---------
1. ``get_fire_data`` returns ``FireHotspot`` and ``ImageFrame`` records.
2. ``get_weather`` returns a ``WeatherSnapshot``.
3. ``predict_spread`` stores ``SpreadForecast`` records that other tools use by id.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from alpineguard.models.domain import Coordinates
from alpineguard.time_utils import to_iso, utc_now


class DetectionConfidence(str, Enum):
    """Confidence of a satellite fire detection."""

    LOW = "low"
    NOMINAL = "nominal"
    HIGH = "high"


class SensorKind(str, Enum):
    """Source of an image frame."""

    DRONE = "drone"
    FIXED_CAMERA = "fixed_camera"


@dataclass
class FireHotspot:
    """A fire detection from a satellite."""

    hotspot_id: str
    location: Coordinates
    detected_at: datetime
    confidence: DetectionConfidence
    fire_radiative_power_mw: float
    source: str
    is_simulated: bool = True

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert the hotspot to a dictionary.

        Returns:
            Hotspot fields with confidence as string.
        """
        return {
            "hotspot_id": self.hotspot_id,
            "location": self.location.to_dict(),
            "detected_at": to_iso(self.detected_at),
            "confidence": self.confidence.value,
            "fire_radiative_power_mw": self.fire_radiative_power_mw,
            "source": self.source,
            "is_simulated": self.is_simulated,
        }


@dataclass
class WeatherSnapshot:
    """Weather at one place; wind direction is where the wind comes from."""

    location: Coordinates
    observed_at: datetime
    wind_speed_kmh: float
    wind_from_deg: float
    gust_kmh: float
    temperature_c: float
    relative_humidity_pct: float
    source: str
    is_simulated: bool = True

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert the weather snapshot to a dictionary.

        Returns:
            Weather fields.
        """
        return {
            "location": self.location.to_dict(),
            "observed_at": to_iso(self.observed_at),
            "wind_speed_kmh": self.wind_speed_kmh,
            "wind_from_deg": self.wind_from_deg,
            "gust_kmh": self.gust_kmh,
            "temperature_c": self.temperature_c,
            "relative_humidity_pct": self.relative_humidity_pct,
            "source": self.source,
            "is_simulated": self.is_simulated,
        }


@dataclass
class ImageFrame:
    """
    One frame from a drone or fixed camera.

    ``image_path`` points to an image file for real Gemini vision analysis. Without it,
    ``scripted_observation`` is the scenario's prepared description of the frame.
    """

    frame_id: str
    sensor_kind: SensorKind
    sensor_name: str
    location: Coordinates
    captured_at: datetime
    scripted_observation: str
    image_path: Optional[str] = None
    is_simulated: bool = True

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert the frame metadata to a dictionary (without the observation text).

        Returns:
            Frame metadata.
        """
        return {
            "frame_id": self.frame_id,
            "sensor_kind": self.sensor_kind.value,
            "sensor_name": self.sensor_name,
            "location": self.location.to_dict(),
            "captured_at": to_iso(self.captured_at),
            "has_image_file": self.image_path is not None,
            "is_simulated": self.is_simulated,
        }


@dataclass
class SpreadGeometry:
    """Raw output of the spread model for one time horizon."""

    polygon: List[Coordinates]
    head_distance_m: float
    flank_distance_m: float
    back_distance_m: float
    length_to_breadth: float


@dataclass
class SpreadForecast:
    """Predicted fire area for one time horizon."""

    forecast_id: str
    incident_id: str
    horizon_minutes: int
    ignition: Coordinates
    polygon: List[Coordinates]
    head_distance_m: float
    flank_distance_m: float
    back_distance_m: float
    downwind_bearing_deg: float
    wind_speed_kmh: float
    wind_from_deg: float
    model_name: str
    model_note: str
    created_at: datetime = field(default_factory=utc_now)

    def to_dict(self, include_polygon: bool = True) -> Dict[str, Any]:
        """
        Convert the forecast to a dictionary.

        Parameters:
            include_polygon: Include the polygon vertices (long) or only their count.

        Returns:
            Forecast fields.
        """
        data: Dict[str, Any] = {
            "forecast_id": self.forecast_id,
            "incident_id": self.incident_id,
            "horizon_minutes": self.horizon_minutes,
            "ignition": self.ignition.to_dict(),
            "head_distance_m": round(self.head_distance_m),
            "flank_distance_m": round(self.flank_distance_m),
            "back_distance_m": round(self.back_distance_m),
            "downwind_bearing_deg": round(self.downwind_bearing_deg),
            "wind_speed_kmh": self.wind_speed_kmh,
            "wind_from_deg": self.wind_from_deg,
            "model_name": self.model_name,
            "model_note": self.model_note,
            "created_at": to_iso(self.created_at),
        }
        if include_polygon:
            data["polygon"] = [
                {"latitude": round(p.latitude, 6), "longitude": round(p.longitude, 6)} for p in self.polygon
            ]
        else:
            data["polygon_vertex_count"] = len(self.polygon)
        return data
