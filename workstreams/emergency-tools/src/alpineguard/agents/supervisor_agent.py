from typing import Dict, Any, List, Optional
import uuid
from alpineguard.models.domain import (
    Incident, IncidentCategory, SeverityLevel, IncidentStatus, Coordinates, MultimodalArtifact
)
from alpineguard.agents.avalanche_agent import AvalancheSurveillanceAgent
from alpineguard.agents.evacuation_agent import EvacuationRouteAgent
from alpineguard.audit import AuditLog
from alpineguard.models.approvals import PendingAction, ProposedAction
from alpineguard.models.multimodal import MultimodalGenerationPipeline
from alpineguard.models.resources import DispatchPriority
from alpineguard.models.tooling import ToolName
from alpineguard.tools.approvals import ApprovalQueue

class SupervisorDispatcherAgent:
    """
    Supervisor Dispatcher Agent:
    - Central coordinator and triage officer for 112 / Cantonal Emergency Operations.
    - Manages lifecycle of incidents: Triage -> Risk Surveillance -> Evacuation Routing -> Responder Dispatch.
    - Coordinates sub-agents and triggers Multimodal Generative Pipelines (Veo 3, Imagen 3, NanoBanana).
    - Produces structured supervisor logs for 112 human-in-the-loop review.
    - Never dispatches or evacuates by itself: dispatch and evacuation wait in the approval
      queue until the 112 operator approves (EU AI Act Annex III 5(d): human oversight).
    """

    def __init__(
        self,
        agent_id: str = "agent-supervisor-112",
        approvals: Optional[ApprovalQueue] = None,
        audit: Optional[AuditLog] = None,
    ):
        self.agent_id = agent_id
        self.avalanche_agent = AvalancheSurveillanceAgent()
        self.evac_agent = EvacuationRouteAgent()
        self.audit = audit or AuditLog()
        self.approvals = approvals or ApprovalQueue(self.audit)

    def process_emergency_signal(
        self,
        caller_id: str,
        category: IncidentCategory,
        canton: str,
        location: str,
        coordinates: Coordinates,
        raw_distress_text: str
    ) -> Dict[str, Any]:
        """
        End-to-end triage, hazard analysis, evacuation calculation, and multimodal
        response package generation. Dispatch and evacuation are proposed to the 112
        operator as pending actions; the incident stays AWAITING_APPROVAL until the
        operator approves them via ``self.approvals``.
        """
        incident_id = f"inc-ch-{uuid.uuid4().hex[:6]}"

        # Step 1: Initial Triage
        incident = Incident(
            id=incident_id,
            category=category,
            severity=SeverityLevel.LEVEL_3_CONSIDERABLE,
            status=IncidentStatus.EVALUATING,
            coordinates=coordinates,
            canton=canton,
            description=raw_distress_text
        )

        supervisor_notes = [
            f"[Triage] Received emergency distress from caller {caller_id[:4]}*** at {location} ({canton}).",
            f"[Triage] Initial assessment: category={category.value}. Activating Avalanche Surveillance Agent."
        ]

        # Step 2: Invoke Avalanche & Alpine Surveillance Agent
        surveillance_result = self.avalanche_agent.assess_alpine_risk(
            canton=canton,
            location=location,
            coords=coordinates
        )

        incident.severity = surveillance_result["recommended_severity"]
        hazard_polygon = [Coordinates(**p) for p in surveillance_result["hazard_polygon"]]
        incident.hazard_polygon = hazard_polygon
        supervisor_notes.append(
            f"[Surveillance] SLF danger level: {surveillance_result['slf_danger_level']}. "
            f"Active avalanche detected={surveillance_result['avalanche_active']}. "
            f"Severity escalated to {incident.severity.name}."
        )

        # Step 3: Invoke Evacuation Route Agent & Multimodal Pipeline
        evac_result = self.evac_agent.plan_evacuation(
            incident_id=incident.id,
            origin=coordinates,
            hazard_polygon=hazard_polygon
        )
        evac_route = evac_result["route"]
        multimodal_artifacts: List[MultimodalArtifact] = evac_result["multimodal_artifacts"]

        supervisor_notes.append(
            f"[Evacuation] Safe path computed to {evac_route.safe_destination_name} "
            f"({evac_route.total_distance_km}km, ~{evac_route.estimated_walking_time_mins} min walk)."
        )
        supervisor_notes.append(
            f"[Multimodal] Generated NanoBanana vector map: {evac_route.vector_map_render_url}"
        )
        supervisor_notes.append(
            f"[Multimodal] Generated Veo 3 3D route fly-through: {evac_route.video_simulation_url}"
        )

        # Step 4: Dispatch Helicopter (Rega 1414) Landing Zone Schematic (Imagen 3)
        lz_coords = Coordinates(latitude=coordinates.latitude + 0.002, longitude=coordinates.longitude + 0.003, altitude_m=coordinates.altitude_m)
        lz_sketch: MultimodalArtifact = MultimodalGenerationPipeline.generate_imagen3_lz_sketch(
            incident_id=incident.id,
            coordinates=lz_coords,
            landing_zone_name=f"{location} North Ridge Clearing"
        )
        multimodal_artifacts.append(lz_sketch)
        supervisor_notes.append(
            f"[Multimodal] Generated Imagen 3 Rega LZ briefing sketch: {lz_sketch.media_url}"
        )

        # Step 5: Ask the 112 operator to approve dispatch and evacuation (nothing happens before approval)
        recommended_units = ["Rega Helicopter Base Erstfeld", "Realp Mountain Rescue Patrol"]
        dispatch_action: PendingAction = self.approvals.submit(
            tool_name=ToolName.PROPOSE_DISPATCH,
            arguments={"incident_id": incident.id, "units": recommended_units,
                       "priority": DispatchPriority.P1_LIFE_THREAT.value},
            reason=(
                f"SLF danger level {surveillance_result['slf_danger_level']}, "
                f"active avalanche={surveillance_result['avalanche_active']}, party at {location} cut off."
            ),
            requested_by=self.agent_id,
            proposal=ProposedAction(
                summary=f"Dispatch {', '.join(recommended_units)} to {location} with priority P1.",
                incident_id=incident.id,
                preview={"units": recommended_units, "rega_lz_briefing_url": lz_sketch.media_url},
                executor=lambda: self._mark_dispatched(incident, recommended_units),
            ),
        )
        evacuation_action: PendingAction = self.approvals.submit(
            tool_name=ToolName.DRAFT_PUBLIC_ALERT,
            arguments={"incident_id": incident.id, "route_id": evac_route.route_id,
                       "safe_destination": evac_route.safe_destination_name},
            reason=surveillance_result["recommended_action"],
            requested_by=self.agent_id,
            proposal=ProposedAction(
                summary=f"Order the evacuation via the ridge route to {evac_route.safe_destination_name}.",
                incident_id=incident.id,
                preview={
                    "route_id": evac_route.route_id,
                    "first_instruction": evac_route.waypoints[0].instruction,
                    "critical_warnings": evac_route.critical_warnings,
                },
                executor=lambda: self._mark_evacuating(incident),
            ),
        )
        incident.status = IncidentStatus.AWAITING_APPROVAL
        pending_actions = [dispatch_action, evacuation_action]
        supervisor_notes.append(
            "[Approval] Dispatch and evacuation wait for the 112 operator: "
            + ", ".join(a.action_id for a in pending_actions) + "."
        )

        return {
            "incident": incident,
            "evacuation_route": evac_route,
            "multimodal_artifacts": multimodal_artifacts,
            "supervisor_action_log": supervisor_notes,
            "pending_approvals": [a.to_dict() for a in pending_actions],
            "action_summary": {
                "civilian_pwa_guidance": {
                    "safe_destination": evac_route.safe_destination_name,
                    "estimated_time_mins": evac_route.estimated_walking_time_mins,
                    "first_instruction": evac_route.waypoints[0].instruction,
                    "vector_map_url": evac_route.vector_map_render_url,
                    "video_flythrough_url": evac_route.video_simulation_url
                },
                "dispatcher_112_console": {
                    "incident_id": incident.id,
                    "severity": incident.severity.name,
                    "canton": incident.canton,
                    "rega_lz_briefing_url": lz_sketch.media_url,
                    "recommended_unit_dispatch": recommended_units,
                    "pending_action_ids": [a.action_id for a in pending_actions]
                }
            }
        }

    @staticmethod
    def _mark_dispatched(incident: Incident, units: List[str]) -> Dict[str, Any]:
        """Executor of the approved dispatch: mark the incident as dispatched."""
        if incident.status in (IncidentStatus.DETECTED, IncidentStatus.EVALUATING, IncidentStatus.AWAITING_APPROVAL):
            incident.status = IncidentStatus.DISPATCHED
        return {"dispatched_units": units, "incident_status": incident.status.value}

    @staticmethod
    def _mark_evacuating(incident: Incident) -> Dict[str, Any]:
        """Executor of the approved evacuation order: mark the incident as evacuating."""
        incident.status = IncidentStatus.EVACUATING
        return {"incident_status": incident.status.value}
