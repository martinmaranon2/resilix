import sys
import os
import unittest

# Ensure src/ is on python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from alpineguard.agents.supervisor_agent import SupervisorDispatcherAgent
from alpineguard.agents.avalanche_agent import AvalancheSurveillanceAgent
from alpineguard.agents.evacuation_agent import EvacuationRouteAgent
from alpineguard.models.domain import (
    IncidentCategory, SeverityLevel, Coordinates, IncidentStatus
)
from alpineguard.models.approvals import ApprovalStatus

class TestAlpineGuardAgents(unittest.TestCase):

    def setUp(self):
        self.supervisor = SupervisorDispatcherAgent()
        self.avalanche_agent = AvalancheSurveillanceAgent()
        self.evac_agent = EvacuationRouteAgent()
        self.test_coords = Coordinates(latitude=46.558, longitude=8.561, altitude_m=2436)

    def test_avalanche_surveillance_agent(self):
        report = self.avalanche_agent.assess_alpine_risk(
            canton="UR",
            location="Furka Pass",
            coords=self.test_coords
        )
        self.assertEqual(report["canton"], "UR")
        self.assertEqual(report["slf_danger_level"], 4)
        self.assertTrue(report["avalanche_active"])
        self.assertGreater(len(report["hazard_polygon"]), 0)
        self.assertIn("crown_fracture_detected", report["vision_diagnostics"][0])

    def test_evacuation_route_agent_with_phase_3_multimodal(self):
        hazard_polygon = [
            Coordinates(latitude=46.56, longitude=8.55, altitude_m=2400),
            Coordinates(latitude=46.57, longitude=8.57, altitude_m=2300),
        ]
        result = self.evac_agent.plan_evacuation(
            incident_id="inc-test-01",
            origin=self.test_coords,
            hazard_polygon=hazard_polygon
        )
        route = result["route"]
        artifacts = result["multimodal_artifacts"]

        self.assertIsNotNone(route.route_id)
        self.assertEqual(route.safe_destination_name, "Realp Civil Defense Emergency Bunker")
        self.assertEqual(len(route.waypoints), 3)
        self.assertIsNotNone(route.vector_map_render_url)
        self.assertIsNotNone(route.video_simulation_url)

        # Verify Phase 3 Multimodal outputs
        artifact_types = [a.artifact_type for a in artifacts]
        self.assertIn("nanobanana_map", artifact_types)
        self.assertIn("veo3_video", artifact_types)

        nanobanana = next(a for a in artifacts if a.artifact_type == "nanobanana_map")
        self.assertIn("svg_preview", nanobanana.metadata)
        self.assertIn("safePath", nanobanana.metadata["svg_preview"])

    def test_supervisor_end_to_end_dispatch(self):
        response = self.supervisor.process_emergency_signal(
            caller_id="+41791234567",
            category=IncidentCategory.AVALANCHE,
            canton="UR",
            location="Furka Pass Summit",
            coordinates=self.test_coords,
            raw_distress_text="Massive avalanche triggered on north face, hiking party of 4 cut off from road."
        )

        incident = response["incident"]
        route = response["evacuation_route"]
        artifacts = response["multimodal_artifacts"]
        summary = response["action_summary"]

        # Nothing is dispatched or evacuated before the 112 operator approves
        self.assertEqual(incident.status, IncidentStatus.AWAITING_APPROVAL)
        self.assertEqual(len(response["pending_approvals"]), 2)
        self.assertEqual(incident.severity, SeverityLevel.LEVEL_4_HIGH)
        self.assertEqual(len(artifacts), 3) # NanoBanana map + Veo3 video + Imagen3 Rega LZ sketch

        # Verify civilian output
        civilian = summary["civilian_pwa_guidance"]
        self.assertIn("Realp Civil Defense", civilian["safe_destination"])
        self.assertIn("vector_map_url", civilian)
        self.assertIn("video_flythrough_url", civilian)

        # Verify dispatcher output
        dispatcher = summary["dispatcher_112_console"]
        self.assertEqual(dispatcher["severity"], "LEVEL_4_HIGH")
        self.assertIn("rega_lz_briefing_url", dispatcher)
        self.assertIn("Rega Helicopter Base Erstfeld", dispatcher["recommended_unit_dispatch"])
        self.assertEqual(dispatcher["pending_action_ids"], [a["action_id"] for a in response["pending_approvals"]])

        # The operator approves both actions; only then the incident is dispatched and evacuating
        for action_id in dispatcher["pending_action_ids"]:
            decided = self.supervisor.approvals.approve(action_id, operator_id="operator-test")
            self.assertEqual(decided.status, ApprovalStatus.EXECUTED)
        self.assertEqual(incident.status, IncidentStatus.EVACUATING)

    def test_supervisor_rejected_actions_change_nothing(self):
        response = self.supervisor.process_emergency_signal(
            caller_id="+41791234567",
            category=IncidentCategory.AVALANCHE,
            canton="UR",
            location="Furka Pass Summit",
            coordinates=self.test_coords,
            raw_distress_text="Avalanche on north face, party of 2 on the ridge."
        )
        incident = response["incident"]
        for action_id in response["action_summary"]["dispatcher_112_console"]["pending_action_ids"]:
            decided = self.supervisor.approvals.reject(action_id, operator_id="operator-test", note="Rega already on site")
            self.assertEqual(decided.status, ApprovalStatus.REJECTED)
            self.assertIsNone(decided.result)
        self.assertEqual(incident.status, IncidentStatus.AWAITING_APPROVAL)
        self.assertEqual(self.supervisor.approvals.pending(), [])

if __name__ == "__main__":
    unittest.main()
