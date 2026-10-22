"""
Cardiac arrest tools.

Architecture
------------
Three tools for the first minutes of a cardiac arrest call, while the voice agent
coaches the caller with the approved CPR protocol:
- find_aed                (agent alone)       nearest public defibrillators with walking time
- alert_first_responders  (operator approves) volunteers near the patient
- find_hospital           (agent alone)       target hospital with the needed capability
AED and volunteer data come from the simulated world; later an AED register
(OpenStreetMap tag emergency=defibrillator) and a first-responder app can fill them.

Use cases
---------
1. The voice agent tells the caller where the nearest AED is (fast tool).
2. The background agent proposes alerting volunteers and an ambulance; the operator approves.
3. The background agent names a hospital with a catheter lab for the ambulance crew.
"""

from typing import Any, Dict, List, Optional

from alpineguard.config import Config
from alpineguard.models.approvals import ProposedAction
from alpineguard.models.domain import Coordinates
from alpineguard.models.resources import HospitalCapability, UnitKind, UnitStatus
from alpineguard.models.tooling import AgentRole, ToolName, ToolSpec, ToolTier
from alpineguard.tools.context import ToolContext
from alpineguard.tools.core_tools import get_incident
from alpineguard.tools.eta import drive_minutes, unit_eta_minutes, urban_walking_minutes
from alpineguard.tools.geo import haversine_m
from alpineguard.tools.results import ToolInputError, ok
from alpineguard.tools.schemas import INCIDENT_ID, LATITUDE, LONGITUDE, MAX_RESULTS, REASON, enum_schema, object_schema


def find_aed(
    ctx: ToolContext,
    latitude: float,
    longitude: float,
    radius_m: Optional[float] = None,
    max_results: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Find public defibrillators near a position.

    Parameters:
        ctx: Tool context.
        latitude: Patient latitude.
        longitude: Patient longitude.
        radius_m: Search radius (default from Config).
        max_results: Maximum number of AEDs.

    Returns:
        AEDs sorted by distance, with one-way walking time and access hint.
    """
    patient = Coordinates(latitude=latitude, longitude=longitude)
    radius = radius_m if radius_m is not None else Config.AED_SEARCH_RADIUS_M
    rows = []
    for aed in ctx.world.aeds():
        distance = haversine_m(patient, aed.location)
        if distance <= radius:
            rows.append({
                **aed.to_dict(),
                "distance_m": round(distance),
                "walking_minutes_one_way": round(urban_walking_minutes(patient, aed.location), 1),
            })
    rows.sort(key=lambda r: r["distance_m"])
    return ok(radius_m=radius, aeds=rows[: max_results or Config.DEFAULT_MAX_RESULTS],
              note="Check 'available_24h' and 'access_hint' before sending someone.")


def alert_first_responders(
    ctx: ToolContext,
    incident_id: str,
    latitude: float,
    longitude: float,
    reason: str,
    radius_m: Optional[float] = None,
) -> ProposedAction:
    """
    Propose alerting volunteer first responders near the patient (needs operator approval).

    Parameters:
        ctx: Tool context.
        incident_id: Cardiac arrest incident.
        latitude: Patient latitude.
        longitude: Patient longitude.
        reason: Why volunteers should go.
        radius_m: Search radius (default from Config).

    Returns:
        Proposed action whose executor alerts the volunteers.

    Raises:
        ToolInputError: If the incident is unknown or no volunteer is available in the radius.
    """
    incident = get_incident(ctx, incident_id)
    patient = Coordinates(latitude=latitude, longitude=longitude)
    radius = radius_m if radius_m is not None else Config.FIRST_RESPONDER_RADIUS_M
    responders = [
        u for u in ctx.world.units(kinds=[UnitKind.FIRST_RESPONDER], statuses=[UnitStatus.AVAILABLE])
        if haversine_m(u.location, patient) <= radius
    ]
    if not responders:
        raise ToolInputError(f"No available first responders within {radius:.0f} m.")
    rows = sorted(
        ({"unit_id": u.unit_id, "name": u.name, "distance_m": round(haversine_m(u.location, patient)),
          "eta_minutes": round(unit_eta_minutes(u.kind, u.location, patient), 1)} for u in responders),
        key=lambda r: r["distance_m"],
    )
    unit_ids = [r["unit_id"] for r in rows]

    def execute() -> Dict[str, Any]:
        alerted = ctx.world.alert_responders(unit_ids, incident.id)
        return {"alerted_unit_ids": [u.unit_id for u in alerted]}

    return ProposedAction(
        summary=f"Alert {len(rows)} volunteer first responder(s) within {radius:.0f} m of the patient "
                f"for incident {incident.id}.",
        incident_id=incident.id,
        preview={"responders": rows, "radius_m": radius},
        executor=execute,
    )


def find_hospital(
    ctx: ToolContext,
    latitude: float,
    longitude: float,
    capability: str,
    max_results: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Find hospitals with a capability, sorted by driving time.

    Parameters:
        ctx: Tool context.
        latitude: Patient latitude.
        longitude: Patient longitude.
        capability: HospitalCapability value.
        max_results: Maximum number of hospitals.

    Returns:
        Hospitals with driving time.
    """
    patient = Coordinates(latitude=latitude, longitude=longitude)
    needed = HospitalCapability(capability)
    rows = [
        {**h.to_dict(), "drive_minutes": round(drive_minutes(patient, h.location), 1)}
        for h in ctx.world.hospitals() if needed in h.capabilities
    ]
    rows.sort(key=lambda r: r["drive_minutes"])
    return ok(capability=needed.value, hospitals=rows[: max_results or Config.DEFAULT_MAX_RESULTS],
              note="Hospital capabilities in the demo scenarios are simulated.")


def specs() -> List[ToolSpec]:
    """
    Describe the cardiac arrest tools for the registry.

    Returns:
        Tool specs of the three cardiac arrest tools.
    """
    return [
        ToolSpec(
            name=ToolName.FIND_AED,
            description="Find public defibrillators (AEDs) near the patient, sorted by distance, with walking time, "
                        "opening hours and access hint.",
            parameters=object_schema({
                "latitude": LATITUDE,
                "longitude": LONGITUDE,
                "radius_m": {"type": "number", "minimum": 50, "maximum": 5000, "description": "Search radius in metres."},
                "max_results": MAX_RESULTS,
            }, ["latitude", "longitude"]),
            tier=ToolTier.AGENT_ALONE, roles=[AgentRole.VOICE, AgentRole.BACKGROUND], handler=find_aed,
        ),
        ToolSpec(
            name=ToolName.ALERT_FIRST_RESPONDERS,
            description="Propose alerting trained volunteer first responders near the patient; they can start CPR and "
                        "bring an AED before the ambulance arrives.",
            parameters=object_schema({
                "incident_id": INCIDENT_ID,
                "latitude": LATITUDE,
                "longitude": LONGITUDE,
                "reason": REASON,
                "radius_m": {"type": "number", "minimum": 100, "maximum": 3000, "description": "Search radius in metres."},
            }, ["incident_id", "latitude", "longitude", "reason"]),
            tier=ToolTier.OPERATOR_APPROVES, roles=[AgentRole.BACKGROUND], handler=alert_first_responders,
        ),
        ToolSpec(
            name=ToolName.FIND_HOSPITAL,
            description="Find hospitals with a required capability (for example a cardiac catheter lab), sorted by "
                        "driving time from the patient.",
            parameters=object_schema({
                "latitude": LATITUDE,
                "longitude": LONGITUDE,
                "capability": enum_schema(HospitalCapability, "Required hospital capability."),
                "max_results": MAX_RESULTS,
            }, ["latitude", "longitude", "capability"]),
            tier=ToolTier.AGENT_ALONE, roles=[AgentRole.BACKGROUND], handler=find_hospital,
        ),
    ]
