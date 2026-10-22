from typing import List, Dict, Any, Optional
from enum import Enum
from datetime import datetime
from dataclasses import dataclass, field

class SeverityLevel(int, Enum):
    LEVEL_1_LOW = 1
    LEVEL_2_MODERATE = 2
    LEVEL_3_CONSIDERABLE = 3
    LEVEL_4_HIGH = 4
    LEVEL_5_VERY_HIGH = 5

class IncidentCategory(str, Enum):
    AVALANCHE = "avalanche"
    WILDFIRE = "wildfire"
    ROCKFALL = "rockfall"
    FLOOD = "flood"
    ALPINE_TRAUMA = "alpine_trauma"

class IncidentStatus(str, Enum):
    DETECTED = "detected"
    EVALUATING = "evaluating"
    DISPATCHED = "dispatched"
    EVACUATING = "evacuating"
    RESOLVED = "resolved"

@dataclass
class Coordinates:
    latitude: float
    longitude: float
    altitude_m: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "latitude": self.latitude,
            "longitude": self.longitude,
            "altitude_m": self.altitude_m
        }

@dataclass
class Incident:
    id: str
    category: IncidentCategory
    severity: SeverityLevel
    status: IncidentStatus
    coordinates: Coordinates
    canton: str
    description: str
    affected_radius_km: float = 2.0
    hazard_polygon: Optional[List[Coordinates]] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "category": self.category.value,
            "severity": self.severity.name,
            "status": self.status.value,
            "coordinates": self.coordinates.to_dict(),
            "canton": self.canton,
            "description": self.description,
            "affected_radius_km": self.affected_radius_km,
            "hazard_polygon": [p.to_dict() for p in self.hazard_polygon] if self.hazard_polygon else []
        }

@dataclass
class EvacuationWaypoint:
    name: str
    coordinates: Coordinates
    instruction: str
    hazard_clearance_m: float
    eta_minutes: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "coordinates": self.coordinates.to_dict(),
            "instruction": self.instruction,
            "hazard_clearance_m": self.hazard_clearance_m,
            "eta_minutes": self.eta_minutes
        }

@dataclass
class EvacuationRoute:
    route_id: str
    incident_id: str
    safe_destination_name: str
    safe_destination_coords: Coordinates
    waypoints: List[EvacuationWaypoint]
    total_distance_km: float
    estimated_walking_time_mins: int
    elevation_drop_m: float
    critical_warnings: List[str]
    vector_map_render_url: Optional[str] = None
    video_simulation_url: Optional[str] = None
    generated_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "route_id": self.route_id,
            "incident_id": self.incident_id,
            "safe_destination_name": self.safe_destination_name,
            "safe_destination_coords": self.safe_destination_coords.to_dict(),
            "waypoints": [w.to_dict() for w in self.waypoints],
            "total_distance_km": self.total_distance_km,
            "estimated_walking_time_mins": self.estimated_walking_time_mins,
            "elevation_drop_m": self.elevation_drop_m,
            "critical_warnings": self.critical_warnings,
            "vector_map_render_url": self.vector_map_render_url,
            "video_simulation_url": self.video_simulation_url
        }

@dataclass
class MultimodalArtifact:
    artifact_id: str
    incident_id: str
    artifact_type: str # "veo3_video", "nanobanana_map", "imagen3_lz_sketch"
    media_url: str
    prompt: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "incident_id": self.incident_id,
            "artifact_type": self.artifact_type,
            "media_url": self.media_url,
            "prompt": self.prompt,
            "metadata": self.metadata
        }
