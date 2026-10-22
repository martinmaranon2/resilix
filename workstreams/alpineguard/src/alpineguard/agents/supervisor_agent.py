from typing import Dict, Any, List, Optional
import uuid
from alpineguard.models.domain import (
    Incident, IncidentCategory, SeverityLevel, IncidentStatus, Coordinates, MultimodalArtifact
)
from alpineguard.agents.avalanche_agent import AvalancheSurveillanceAgent
from alpineguard.agents.evacuation_agent import EvacuationRouteAgent
from alpineguard.models.multimodal import MultimodalGenerationPipeline

class SupervisorDispatcherAgent:
    """
    Supervisor Dispatcher Agent:
    - Central coordinator and triage officer for 112 / Cantonal Emergency Operations.
    - Manages lifecycle of incidents: Triage -> Risk Surveillance -> Evacuation Routing -> Responder Dispatch.
    - Coordinates sub-agents and triggers Multimodal Generative Pipelines (Veo 3, Imagen 3, NanoBanana).
    - Produces structured supervisor logs for 112 human-in-the-loop review.
    """

    def __init__(self, agent_id: str = "agent-supervisor-112"):
        self.agent_id = agent_id
        self.avalanche_agent = AvalancheSurveillanceAgent()
        self.evac_agent = EvacuationRouteAgent()

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
        End-to-end autonomous triage, hazard analysis, evacuation calculation,
        and multimodal response package generation.
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

        # Step 5: Update Incident Status
        incident.status = IncidentStatus.EVACUATING

        return {
            "incident": incident,
            "evacuation_route": evac_route,
            "multimodal_artifacts": multimodal_artifacts,
            "supervisor_action_log": supervisor_notes,
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
                    "recommended_unit_dispatch": ["Rega Helicopter Base Erstfeld", "Realp Mountain Rescue Patrol"]
                }
            }
        }
