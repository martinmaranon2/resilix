"""
Core tools used for every incident type.

Architecture
------------
Eight tools that every emergency needs:
- locate_caller          (agent alone)       caller position from AML
- update_incident        (agent alone)       structured incident card, PII removed
- find_related_incidents (agent alone)       calls/posts/incidents about the same event
- get_protocol           (agent alone)       approved questions and caller instructions
- list_units             (agent alone)       available units sorted by ETA
- propose_dispatch       (operator approves) send units with a priority
- notify_centre          (agent alone)       information to another centre (no requests)
- handoff_to_operator    (agent alone)       a human takes over now
Each handler receives the ``ToolContext`` first and returns a JSON-ready dictionary,
or a ``ProposedAction`` for approval-tier tools. ``specs()`` describes the tools for the
registry.

Use cases
---------
1. Voice agent: locate the caller, write the incident card, read the protocol, hand off.
2. Background agent: merge reports, list units, propose dispatch, inform other centres.
"""

from typing import Any, Dict, List, Optional

from alpineguard.config import Config
from alpineguard.models.approvals import ProposedAction
from alpineguard.models.calls import CentreMessage, EmergencyCentre, HandoffRequest, HandoffUrgency
from alpineguard.models.domain import Coordinates, Incident, IncidentCategory, IncidentStatus, SeverityLevel
from alpineguard.models.resources import DispatchPriority, UnitKind, UnitStatus
from alpineguard.models.tooling import AgentRole, ToolName, ToolSpec, ToolTier
from alpineguard.time_utils import to_iso, utc_now
from alpineguard.tools.context import ToolContext
from alpineguard.tools.eta import unit_eta_minutes
from alpineguard.tools.geo import haversine_m
from alpineguard.tools.privacy import scrub_pii
from alpineguard.tools.protocol_store import load_protocol
from alpineguard.tools.results import ToolInputError, error, new_id, ok
from alpineguard.tools.schemas import INCIDENT_ID, LATITUDE, LONGITUDE, MAX_RESULTS, REASON, enum_schema, object_schema


def get_incident(ctx: ToolContext, incident_id: str) -> Incident:
    """
    Look up an incident created by update_incident.

    Parameters:
        ctx: Tool context.
        incident_id: Incident id.

    Returns:
        The incident.

    Raises:
        ToolInputError: If the id is unknown (the message lists known ids).
    """
    incident = ctx.incidents.get(incident_id)
    if incident is None:
        raise ToolInputError(f"Unknown incident_id '{incident_id}'. Known incidents: {sorted(ctx.incidents)}")
    return incident


def locate_caller(ctx: ToolContext, call_id: str) -> Dict[str, Any]:
    """
    Return the caller position of a call.

    Parameters:
        ctx: Tool context.
        call_id: Call id.

    Returns:
        Position, accuracy, position source and address hint.
    """
    call = ctx.world.find_call(call_id)
    if call is None:
        return error(f"Unknown call_id '{call_id}'. Known calls: {[c.call_id for c in ctx.world.calls()]}")
    return ok(**call.to_dict())


def update_incident(
    ctx: ToolContext,
    category: str,
    description: str,
    latitude: float,
    longitude: float,
    severity: int,
    call_ids: List[str],
    incident_id: Optional[str] = None,
    persons_involved: Optional[int] = None,
    hazards: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Create or update the incident card.

    Parameters:
        ctx: Tool context.
        category: IncidentCategory value.
        description: Short factual summary; phone numbers and e-mails are removed.
        latitude: Incident latitude.
        longitude: Incident longitude.
        severity: Proposed severity 1-5.
        call_ids: Calls that report this incident.
        incident_id: Existing incident to update; a new incident is created when None.
        persons_involved: Number of people involved, if known.
        hazards: Short hazard notes, for example "flames near rail line".

    Returns:
        The incident card.

    Raises:
        ToolInputError: If a call id or the incident id is unknown.
    """
    unknown_calls = [cid for cid in call_ids if ctx.world.find_call(cid) is None]
    if unknown_calls:
        raise ToolInputError(f"Unknown call ids {unknown_calls}")
    clean_description = scrub_pii(description)
    clean_hazards = [scrub_pii(h) for h in (hazards or [])]
    position = Coordinates(latitude=latitude, longitude=longitude)
    if incident_id is None:
        # one incident per call: a second agent working on the same call updates the existing card
        existing = next((i for i in ctx.incidents.values() if set(i.call_ids) & set(call_ids)), None)
        if existing is not None:
            incident_id = existing.id
    if incident_id is None:
        incident = Incident(
            id=new_id("inc"),
            category=IncidentCategory(category),
            severity=SeverityLevel(severity),
            status=IncidentStatus.EVALUATING,
            coordinates=position,
            canton=ctx.world.canton,
            description=clean_description,
        )
        ctx.incidents[incident.id] = incident
    else:
        incident = get_incident(ctx, incident_id)
        incident.category = IncidentCategory(category)
        incident.severity = SeverityLevel(severity)
        incident.coordinates = position
        incident.description = clean_description
    incident.call_ids = sorted(set(incident.call_ids) | set(call_ids))
    if persons_involved is not None:
        incident.persons_involved = persons_involved
    if hazards is not None:
        incident.hazards = clean_hazards
    incident.updated_at = utc_now()
    return ok(
        incident=incident.to_dict(),
        note="Severity is a proposal. Actions happen only after operator approval.",
    )


def find_related_incidents(
    ctx: ToolContext,
    latitude: float,
    longitude: float,
    radius_m: Optional[float] = None,
    since_minutes: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Find calls, posts and incidents near a position in a recent time window.

    Parameters:
        ctx: Tool context.
        latitude: Search centre latitude.
        longitude: Search centre longitude.
        radius_m: Search radius (default from Config).
        since_minutes: Time window back from now (default from Config).

    Returns:
        Calls with scrubbed transcripts, social media posts and existing incidents.
    """
    centre = Coordinates(latitude=latitude, longitude=longitude)
    radius = radius_m if radius_m is not None else Config.RELATED_INCIDENT_RADIUS_M
    window = since_minutes if since_minutes is not None else Config.RELATED_INCIDENT_WINDOW_MINUTES
    now = ctx.world.now()

    calls = []
    for call in ctx.world.calls():
        age_min = (now - call.received_at).total_seconds() / 60
        distance = haversine_m(centre, call.location)
        if 0 <= age_min <= window and distance <= radius:
            calls.append({
                **call.to_dict(),
                "distance_m": round(distance),
                "minutes_ago": round(age_min, 1),
                "transcript": [scrub_pii(line) for line in call.transcript],
            })
    posts = []
    for post in ctx.world.social_posts():
        age_min = (now - post.posted_at).total_seconds() / 60
        distance = haversine_m(centre, post.location) if post.location else None
        if 0 <= age_min <= window and (distance is None or distance <= radius):
            posts.append({**post.to_dict(), "text": scrub_pii(post.text),
                          "distance_m": round(distance) if distance is not None else None})
    incidents = [
        {"incident_id": i.id, "category": i.category.value, "status": i.status.value,
         "distance_m": round(haversine_m(centre, i.coordinates)), "call_ids": i.call_ids}
        for i in ctx.incidents.values() if haversine_m(centre, i.coordinates) <= radius
    ]
    return ok(radius_m=radius, window_minutes=window, scenario_time=to_iso(now),
              calls=sorted(calls, key=lambda c: c["received_at"]), social_posts=posts, incidents=incidents)


def get_protocol(ctx: ToolContext, category: str) -> Dict[str, Any]:
    """
    Return the approved protocol of an incident category.

    Parameters:
        ctx: Tool context.
        category: IncidentCategory value.

    Returns:
        Protocol with sources, questions and instructions, or an error when none exists.
    """
    protocol = load_protocol(IncidentCategory(category))
    if protocol is None:
        return error(
            f"No approved protocol for category '{category}'. Do not invent instructions; "
            "call handoff_to_operator."
        )
    return ok(protocol=protocol.to_dict())


def list_units(
    ctx: ToolContext,
    latitude: float,
    longitude: float,
    kinds: Optional[List[str]] = None,
    max_results: Optional[int] = None,
) -> Dict[str, Any]:
    """
    List available units sorted by estimated arrival time.

    Parameters:
        ctx: Tool context.
        latitude: Incident latitude.
        longitude: Incident longitude.
        kinds: UnitKind values to include (all kinds when None).
        max_results: Maximum number of units.

    Returns:
        Units with distance and ETA.
    """
    target = Coordinates(latitude=latitude, longitude=longitude)
    kind_filter = [UnitKind(k) for k in kinds] if kinds else None
    rows = []
    for unit in ctx.world.units(kinds=kind_filter, statuses=[UnitStatus.AVAILABLE]):
        rows.append({
            "unit_id": unit.unit_id,
            "name": unit.name,
            "kind": unit.kind.value,
            "centre": unit.centre.value,
            "distance_km": round(haversine_m(unit.location, target) / 1000, 2),
            "eta_minutes": round(unit_eta_minutes(unit.kind, unit.location, target), 1),
            "is_simulated": unit.is_simulated,
        })
    rows.sort(key=lambda r: r["eta_minutes"])
    return ok(
        units=rows[: max_results or Config.DEFAULT_MAX_RESULTS],
        eta_note="Estimate: straight-line distance x road factor at average speed, plus turnout time.",
    )


def propose_dispatch(
    ctx: ToolContext, incident_id: str, unit_ids: List[str], priority: str, reason: str
) -> ProposedAction:
    """
    Propose sending units to an incident (needs operator approval).

    Parameters:
        ctx: Tool context.
        incident_id: Target incident.
        unit_ids: Units to send.
        priority: DispatchPriority value.
        reason: Why these units.

    Returns:
        Proposed action whose executor dispatches the units.

    Raises:
        ToolInputError: If the incident or a unit is unknown, or a unit is not available.
    """
    incident = get_incident(ctx, incident_id)
    rows = []
    for unit_id in unit_ids:
        unit = ctx.world.find_unit(unit_id)
        if unit is None:
            raise ToolInputError(f"Unknown unit_id '{unit_id}'. Use list_units first.")
        if unit.status != UnitStatus.AVAILABLE:
            raise ToolInputError(f"Unit '{unit_id}' is not available (status: {unit.status.value}).")
        rows.append({
            "unit_id": unit.unit_id, "name": unit.name, "kind": unit.kind.value, "centre": unit.centre.value,
            "eta_minutes": round(unit_eta_minutes(unit.kind, unit.location, incident.coordinates), 1),
        })
    dispatch_priority = DispatchPriority(priority)

    def execute() -> Dict[str, Any]:
        dispatched = ctx.world.dispatch_units(unit_ids, incident.id)
        if incident.status in (IncidentStatus.DETECTED, IncidentStatus.EVALUATING, IncidentStatus.AWAITING_APPROVAL):
            incident.status = IncidentStatus.DISPATCHED
        return {"dispatched_unit_ids": [u.unit_id for u in dispatched], "incident_status": incident.status.value}

    return ProposedAction(
        summary=f"Dispatch {', '.join(r['name'] for r in rows)} to incident {incident.id} "
                f"({incident.category.value}) with priority {dispatch_priority.value}.",
        incident_id=incident.id,
        preview={"units": rows, "priority": dispatch_priority.value},
        executor=execute,
    )


def notify_centre(ctx: ToolContext, centre: str, incident_id: str, message: str) -> Dict[str, Any]:
    """
    Send information about an incident to another emergency centre.

    Parameters:
        ctx: Tool context.
        centre: EmergencyCentre value.
        incident_id: Incident the information is about.
        message: Information text; phone numbers and e-mails are removed.

    Returns:
        Delivery confirmation.
    """
    incident = get_incident(ctx, incident_id)
    note = CentreMessage(
        message_id=new_id("msg"),
        centre=EmergencyCentre(centre),
        incident_id=incident.id,
        text=scrub_pii(message),
        sent_at=utc_now(),
        sent_by="agent",
    )
    ctx.world.deliver_centre_message(note)
    return ok(message=note.to_dict(),
              note="Information only. To request units of that centre use propose_dispatch.")


def handoff_to_operator(
    ctx: ToolContext,
    reason: str,
    urgency: str,
    incident_id: Optional[str] = None,
    call_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Ask a human operator to take over.

    Parameters:
        ctx: Tool context.
        reason: Why a human must take over.
        urgency: HandoffUrgency value.
        incident_id: Incident concerned, if any.
        call_id: Call concerned, if any.

    Returns:
        Hand-off confirmation.
    """
    if incident_id is not None:
        get_incident(ctx, incident_id)
    request = HandoffRequest(
        handoff_id=new_id("handoff"),
        reason=scrub_pii(reason),
        urgency=HandoffUrgency(urgency),
        created_at=utc_now(),
        incident_id=incident_id,
        call_id=call_id,
    )
    ctx.world.record_handoff(request)
    return ok(handoff=request.to_dict(), note="A human operator takes over. Tell the caller that a person will speak with them now.")


def specs() -> List[ToolSpec]:
    """
    Describe the core tools for the registry.

    Returns:
        Tool specs of the eight core tools.
    """
    both = [AgentRole.VOICE, AgentRole.BACKGROUND]
    background = [AgentRole.BACKGROUND]
    return [
        ToolSpec(
            name=ToolName.LOCATE_CALLER,
            description="Get the caller position for a call: AML position (the phone sends its GPS position with an "
                        "emergency call), accuracy and address hint.",
            parameters=object_schema({"call_id": {"type": "string", "description": "Call id."}}, ["call_id"]),
            tier=ToolTier.AGENT_ALONE, roles=both, handler=locate_caller,
        ),
        ToolSpec(
            name=ToolName.UPDATE_INCIDENT,
            description="Create the incident card for one emergency, or update it when incident_id is given. Put all "
                        "calls about the same event into one incident. If a call already belongs to an incident, that "
                        "incident is updated. The description is a short factual summary "
                        "without names or phone numbers. Severity 1-5 is your proposal.",
            parameters=object_schema({
                "category": enum_schema(IncidentCategory, "Incident category."),
                "description": {"type": "string", "description": "Short factual summary without personal data."},
                "latitude": LATITUDE,
                "longitude": LONGITUDE,
                "severity": {"type": "integer", "description": "Proposed severity, 1 (low) to 5 (very high).", "minimum": 1, "maximum": 5},
                "call_ids": {"type": "array", "items": {"type": "string"}, "minItems": 1, "description": "Calls that report this incident."},
                "incident_id": {"type": "string", "description": "Existing incident to update. Leave out to create a new incident."},
                "persons_involved": {"type": "integer", "minimum": 0, "description": "Number of people involved, if known."},
                "hazards": {"type": "array", "items": {"type": "string"}, "description": "Short hazard notes."},
            }, ["category", "description", "latitude", "longitude", "severity", "call_ids"]),
            tier=ToolTier.AGENT_ALONE, roles=both, handler=update_incident,
        ),
        ToolSpec(
            name=ToolName.FIND_RELATED_INCIDENTS,
            description="Find other calls (with transcripts), social media posts and existing incidents near a position "
                        "in the last minutes, to merge reports about the same event.",
            parameters=object_schema({
                "latitude": LATITUDE,
                "longitude": LONGITUDE,
                "radius_m": {"type": "number", "minimum": 50, "maximum": 20000, "description": "Search radius in metres."},
                "since_minutes": {"type": "integer", "minimum": 1, "maximum": 240, "description": "Time window in minutes."},
            }, ["latitude", "longitude"]),
            tier=ToolTier.AGENT_ALONE, roles=background, handler=find_related_incidents,
        ),
        ToolSpec(
            name=ToolName.GET_PROTOCOL,
            description="Get the approved questions and caller instructions for an incident category. Give callers only "
                        "instructions from this protocol.",
            parameters=object_schema({"category": enum_schema(IncidentCategory, "Incident category.")}, ["category"]),
            tier=ToolTier.AGENT_ALONE, roles=both, handler=get_protocol,
        ),
        ToolSpec(
            name=ToolName.LIST_UNITS,
            description="List available units (ambulances, fire engines, helicopters, police, volunteers, drones) near a "
                        "position, sorted by estimated arrival time.",
            parameters=object_schema({
                "latitude": LATITUDE,
                "longitude": LONGITUDE,
                "kinds": {"type": "array", "items": enum_schema(UnitKind, "Unit kind."), "description": "Unit kinds to include; all when empty."},
                "max_results": MAX_RESULTS,
            }, ["latitude", "longitude"]),
            tier=ToolTier.AGENT_ALONE, roles=background, handler=list_units,
        ),
        ToolSpec(
            name=ToolName.PROPOSE_DISPATCH,
            description="Propose sending available units to an incident with a dispatch priority.",
            parameters=object_schema({
                "incident_id": INCIDENT_ID,
                "unit_ids": {"type": "array", "items": {"type": "string"}, "minItems": 1, "description": "Unit ids from list_units."},
                "priority": enum_schema(DispatchPriority, "P1 = life threat, P2 = urgent, P3 = not urgent."),
                "reason": REASON,
            }, ["incident_id", "unit_ids", "priority", "reason"]),
            tier=ToolTier.OPERATOR_APPROVES, roles=background, handler=propose_dispatch,
        ),
        ToolSpec(
            name=ToolName.NOTIFY_CENTRE,
            description="Send information about an incident to another emergency centre (117 police, 118 fire, "
                        "144 ambulance, 145 poison, 1414 Rega). Information only; to request their units use propose_dispatch.",
            parameters=object_schema({
                "centre": enum_schema(EmergencyCentre, "Emergency number of the centre."),
                "incident_id": INCIDENT_ID,
                "message": {"type": "string", "description": "Information for the centre, without personal data."},
            }, ["centre", "incident_id", "message"]),
            tier=ToolTier.AGENT_ALONE, roles=background, handler=notify_centre,
        ),
        ToolSpec(
            name=ToolName.HANDOFF_TO_OPERATOR,
            description="Ask a human operator to take over now. Use it when facts conflict, when you are unsure, when no "
                        "approved protocol exists, or when the caller is in a situation the tools do not cover.",
            parameters=object_schema({
                "reason": {"type": "string", "description": "Why a human must take over."},
                "urgency": enum_schema(HandoffUrgency, "How fast the operator must take over."),
                "incident_id": {"type": "string", "description": "Incident concerned, if any."},
                "call_id": {"type": "string", "description": "Call concerned, if any."},
            }, ["reason", "urgency"]),
            tier=ToolTier.AGENT_ALONE, roles=both, handler=handoff_to_operator,
        ),
    ]
