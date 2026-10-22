"""
Response resources: units, defibrillators and hospitals.

Architecture
------------
Units are the vehicles, aircraft, drones and volunteers that the centres can send.
Defibrillators (AEDs) and hospitals are fixed resources. The simulated world loads all
of them from scenario files; later the teammate data layer (``crisis_data``) can fill
hospitals from OpenStreetMap and a unit register can fill units.

Use cases
---------
1. ``list_units`` and ``propose_dispatch`` work with ``Unit`` and ``UnitStatus``.
2. ``find_aed`` and ``alert_first_responders`` serve cardiac arrest calls.
3. ``find_hospital`` filters hospitals by ``HospitalCapability``.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, FrozenSet, List, Optional

from alpineguard.models.calls import EmergencyCentre
from alpineguard.models.domain import Coordinates


class UnitKind(str, Enum):
    """Kind of response unit."""

    AMBULANCE = "ambulance"
    FIRE_ENGINE = "fire_engine"
    FIREFIGHTING_HELICOPTER = "firefighting_helicopter"
    POLICE_PATROL = "police_patrol"
    REGA_HELICOPTER = "rega_helicopter"
    FIRST_RESPONDER = "first_responder"  # trained volunteer alerted by app
    DRONE = "drone"


# Airborne units fly the straight-line distance; ground units follow roads.
AIRBORNE_UNIT_KINDS: FrozenSet[UnitKind] = frozenset(
    {UnitKind.FIREFIGHTING_HELICOPTER, UnitKind.REGA_HELICOPTER, UnitKind.DRONE}
)


class UnitStatus(str, Enum):
    """Availability of a unit."""

    AVAILABLE = "available"
    ALERTED = "alerted"        # volunteer asked to go, not yet confirmed
    DISPATCHED = "dispatched"
    BUSY = "busy"


class DispatchPriority(str, Enum):
    """Dispatch priority proposed by the agent and confirmed by the operator."""

    P1_LIFE_THREAT = "P1"
    P2_URGENT = "P2"
    P3_NOT_URGENT = "P3"


class HospitalCapability(str, Enum):
    """Special units that decide the target hospital."""

    EMERGENCY_DEPARTMENT = "emergency_department"
    CARDIAC_CATH_LAB = "cardiac_cath_lab"
    STROKE_UNIT = "stroke_unit"
    BURNS_UNIT = "burns_unit"
    TRAUMA_CENTRE = "trauma_centre"


@dataclass
class Unit:
    """A unit that a centre can send."""

    unit_id: str
    name: str
    kind: UnitKind
    centre: EmergencyCentre
    location: Coordinates
    status: UnitStatus
    assigned_incident_id: Optional[str] = None
    is_simulated: bool = True

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert the unit to a dictionary.

        Returns:
            Unit fields with enums as values.
        """
        return {
            "unit_id": self.unit_id,
            "name": self.name,
            "kind": self.kind.value,
            "centre": self.centre.value,
            "location": self.location.to_dict(),
            "status": self.status.value,
            "assigned_incident_id": self.assigned_incident_id,
            "is_simulated": self.is_simulated,
        }


@dataclass
class Aed:
    """A public automated external defibrillator."""

    aed_id: str
    name: str
    location: Coordinates
    access_hint: str
    available_24h: bool
    is_simulated: bool = True

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert the AED record to a dictionary.

        Returns:
            AED fields.
        """
        return {
            "aed_id": self.aed_id,
            "name": self.name,
            "location": self.location.to_dict(),
            "access_hint": self.access_hint,
            "available_24h": self.available_24h,
            "is_simulated": self.is_simulated,
        }


@dataclass
class Hospital:
    """A hospital and its special units."""

    hospital_id: str
    name: str
    location: Coordinates
    capabilities: List[HospitalCapability]
    capabilities_simulated: bool = True

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert the hospital to a dictionary.

        Returns:
            Hospital fields with capabilities as strings.
        """
        return {
            "hospital_id": self.hospital_id,
            "name": self.name,
            "location": self.location.to_dict(),
            "capabilities": [c.value for c in self.capabilities],
            "capabilities_simulated": self.capabilities_simulated,
        }
