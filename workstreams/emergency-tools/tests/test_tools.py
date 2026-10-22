"""
Unit tests for the agent tool layer (no network, no Gemini).

Covers: registry and function declarations, argument checks, the approval gate,
the cardiac arrest tools on the Zürich HB scenario, the forest fire tools on the
Uetliberg scenario, personal-data removal, routing safety and the route card.
"""

import logging
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from alpineguard.config import Config
from alpineguard.models.approvals import ApprovalStatus
from alpineguard.models.domain import Coordinates, IncidentStatus
from alpineguard.models.exposure import TrainStatus, AssetStatus
from alpineguard.models.resources import UnitStatus
from alpineguard.models.tooling import AgentRole, ToolName, ToolTier
from alpineguard.simulation.world import SimulatedWorld
from alpineguard.tools.context import ToolContext
from alpineguard.tools.geo import distance_to_polygon_m, haversine_m, point_in_polygon, segment_crosses_polygon
from alpineguard.tools.privacy import scrub_pii
from alpineguard.tools.registry import build_registry

logging.getLogger("alpineguard").setLevel(logging.WARNING)

BACKGROUND = AgentRole.BACKGROUND
APPROVAL_TOOLS = {ToolName.PROPOSE_DISPATCH, ToolName.ALERT_FIRST_RESPONDERS,
                  ToolName.DRAFT_PUBLIC_ALERT, ToolName.REQUEST_INFRA_ACTION}
VOICE_TOOLS = {ToolName.LOCATE_CALLER, ToolName.UPDATE_INCIDENT, ToolName.GET_PROTOCOL,
               ToolName.HANDOFF_TO_OPERATOR, ToolName.FIND_AED}
HB = Coordinates(latitude=47.37795, longitude=8.54025)
UTO_KULM = Coordinates(latitude=47.34978, longitude=8.49084)


def make_registry(scenario_id):
    ctx = ToolContext.for_world(SimulatedWorld.load(scenario_id))
    return ctx, build_registry(ctx)


class TestRegistry(unittest.TestCase):

    def setUp(self):
        self.ctx, self.registry = make_registry("cardiac_arrest_zurich_hb")

    def test_twenty_tools_with_valid_declarations(self):
        specs = self.registry.specs()
        self.assertEqual(len(specs), 20)
        self.assertEqual({s.name for s in specs}, set(ToolName))
        for declaration in self.registry.declarations(BACKGROUND):
            schema = declaration["parameters"]
            self.assertEqual(schema["type"], "object")
            self.assertTrue(set(schema["required"]) <= set(schema["properties"]), declaration["name"])
            self.assertGreater(len(declaration["description"]), 40)

    def test_tiers_and_roles(self):
        approval = {s.name for s in self.registry.specs() if s.tier == ToolTier.OPERATOR_APPROVES}
        self.assertEqual(approval, APPROVAL_TOOLS)
        self.assertEqual({s.name for s in self.registry.specs(AgentRole.VOICE)}, VOICE_TOOLS)
        for declaration in self.registry.declarations(BACKGROUND):
            if ToolName(declaration["name"]) in APPROVAL_TOOLS:
                self.assertIn("Needs operator approval", declaration["description"])
                self.assertIn("reason", declaration["parameters"]["required"])

    def test_role_check(self):
        result = self.registry.execute("list_units", {"latitude": 47.37, "longitude": 8.54}, AgentRole.VOICE)
        self.assertEqual(result["status"], "error")
        self.assertIn("not available to the voice agent", result["error"])

    def test_argument_checks(self):
        unknown = self.registry.execute("launch_rocket", {}, BACKGROUND)
        self.assertIn("Unknown tool", unknown["error"])
        missing = self.registry.execute("find_aed", {"latitude": 47.37}, BACKGROUND)
        self.assertIn("missing required argument 'longitude'", missing["error"])
        bad_enum = self.registry.execute("find_hospital", {"latitude": 47.37, "longitude": 8.54, "capability": "x_ray"}, BACKGROUND)
        self.assertIn("must be one of", bad_enum["error"])
        extra = self.registry.execute("find_aed", {"latitude": 47.37, "longitude": 8.54, "colour": "red"}, BACKGROUND)
        self.assertIn("unknown argument 'colour'", extra["error"])
        out_of_range = self.registry.execute("update_incident", {
            "category": "cardiac_arrest", "description": "x", "latitude": 47.37, "longitude": 8.54,
            "severity": 7, "call_ids": ["call-hb-001"]}, BACKGROUND)
        self.assertIn("'severity' must be <= 5", out_of_range["error"])

    def test_integer_sent_as_float_is_accepted(self):
        result = self.registry.execute("find_aed", {"latitude": 47.37795, "longitude": 8.54025, "max_results": 2.0}, BACKGROUND)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(len(result["aeds"]), 2)

    def test_every_call_is_audited(self):
        self.registry.execute("locate_caller", {"call_id": "call-hb-001"}, AgentRole.VOICE)
        self.registry.execute("locate_caller", {"call_id": "nope"}, AgentRole.VOICE)
        entries = self.ctx.audit.entries()
        self.assertEqual([e.details["status"] for e in entries], ["ok", "error"])
        self.assertEqual(entries[0].actor, "voice_agent")


class TestCardiacArrestTools(unittest.TestCase):

    def setUp(self):
        self.ctx, self.registry = make_registry("cardiac_arrest_zurich_hb")
        result = self.registry.execute("update_incident", {
            "category": "cardiac_arrest",
            "description": "Man about 60 collapsed in the main hall, gasping. Caller number 079 384 19 28.",
            "latitude": HB.latitude, "longitude": HB.longitude, "severity": 5, "call_ids": ["call-hb-001"],
            "persons_involved": 1}, AgentRole.VOICE)
        self.incident_id = result["incident"]["id"]

    def test_locate_caller(self):
        result = self.registry.execute("locate_caller", {"call_id": "call-hb-001"}, AgentRole.VOICE)
        self.assertEqual(result["location_source"], "aml")
        self.assertEqual(result["location_accuracy_m"], 12)
        self.assertNotIn("transcript", result)

    def test_incident_card_has_no_phone_number(self):
        incident = self.ctx.incidents[self.incident_id]
        self.assertNotIn("079 384 19 28", incident.description)
        self.assertIn("[phone number removed]", incident.description)
        self.assertEqual(incident.status, IncidentStatus.EVALUATING)

    def test_protocol_has_sources_and_demo_label(self):
        result = self.registry.execute("get_protocol", {"category": "cardiac_arrest"}, AgentRole.VOICE)
        protocol = result["protocol"]
        self.assertIn("DEMO CONTENT", protocol["approval_status"])
        self.assertTrue(any("2025" in s["title"] for s in protocol["sources"]))
        self.assertTrue(any("100 to 120" in step for step in protocol["instructions"]))

    def test_missing_protocol_tells_agent_to_hand_off(self):
        result = self.registry.execute("get_protocol", {"category": "flood"}, AgentRole.VOICE)
        self.assertEqual(result["status"], "error")
        self.assertIn("handoff_to_operator", result["error"])

    def test_find_aed_sorted_and_within_radius(self):
        result = self.registry.execute("find_aed", {"latitude": HB.latitude, "longitude": HB.longitude}, AgentRole.VOICE)
        distances = [a["distance_m"] for a in result["aeds"]]
        self.assertEqual(distances, sorted(distances))
        self.assertEqual(result["aeds"][0]["aed_id"], "aed-1")
        self.assertNotIn("aed-5", [a["aed_id"] for a in result["aeds"]])
        self.assertTrue(all(d <= Config.AED_SEARCH_RADIUS_M for d in distances))

    def test_list_units_only_available_and_sorted(self):
        result = self.registry.execute("list_units", {"latitude": HB.latitude, "longitude": HB.longitude,
                                                      "kinds": ["ambulance"]}, BACKGROUND)
        ids = [u["unit_id"] for u in result["units"]]
        self.assertNotIn("amb-05", ids)  # busy
        self.assertEqual(ids[0], "amb-11")
        etas = [u["eta_minutes"] for u in result["units"]]
        self.assertEqual(etas, sorted(etas))

    def test_dispatch_waits_for_approval(self):
        pending = self.registry.execute("propose_dispatch", {
            "incident_id": self.incident_id, "unit_ids": ["amb-11"], "priority": "P1",
            "reason": "Cardiac arrest, nearest ambulance 3 min away"}, BACKGROUND)
        self.assertEqual(pending["status"], "pending_approval")
        self.assertEqual(self.ctx.world.find_unit("amb-11").status, UnitStatus.AVAILABLE)
        self.assertEqual(self.ctx.incidents[self.incident_id].status, IncidentStatus.AWAITING_APPROVAL)

        with self.assertRaises(ValueError):
            self.ctx.approvals.approve(pending["action_id"], operator_id=" ")
        decided = self.ctx.approvals.approve(pending["action_id"], operator_id="op-17")
        self.assertEqual(decided.status, ApprovalStatus.EXECUTED)
        self.assertEqual(decided.decided_by, "op-17")
        self.assertEqual(self.ctx.world.find_unit("amb-11").status, UnitStatus.DISPATCHED)
        self.assertEqual(self.ctx.incidents[self.incident_id].status, IncidentStatus.DISPATCHED)
        with self.assertRaises(ValueError):
            self.ctx.approvals.approve(pending["action_id"], operator_id="op-17")

    def test_rejected_dispatch_changes_nothing(self):
        pending = self.registry.execute("propose_dispatch", {
            "incident_id": self.incident_id, "unit_ids": ["amb-23"], "priority": "P1", "reason": "x"}, BACKGROUND)
        decided = self.ctx.approvals.reject(pending["action_id"], operator_id="op-17", note="amb-11 is closer")
        self.assertEqual(decided.status, ApprovalStatus.REJECTED)
        self.assertEqual(self.ctx.world.find_unit("amb-23").status, UnitStatus.AVAILABLE)

    def test_dispatch_of_busy_unit_is_refused(self):
        result = self.registry.execute("propose_dispatch", {
            "incident_id": self.incident_id, "unit_ids": ["amb-05"], "priority": "P1", "reason": "x"}, BACKGROUND)
        self.assertEqual(result["status"], "error")
        self.assertIn("not available", result["error"])

    def test_unit_taken_between_proposal_and_approval_fails_cleanly(self):
        first = self.registry.execute("propose_dispatch", {
            "incident_id": self.incident_id, "unit_ids": ["amb-11"], "priority": "P1", "reason": "x"}, BACKGROUND)
        second = self.registry.execute("propose_dispatch", {
            "incident_id": self.incident_id, "unit_ids": ["amb-11"], "priority": "P1", "reason": "x"}, BACKGROUND)
        self.ctx.approvals.approve(first["action_id"], operator_id="op-17")
        failed = self.ctx.approvals.approve(second["action_id"], operator_id="op-17")
        self.assertEqual(failed.status, ApprovalStatus.FAILED)
        self.assertIn("not available", failed.error)

    def test_first_responders_within_radius_after_approval(self):
        pending = self.registry.execute("alert_first_responders", {
            "incident_id": self.incident_id, "latitude": HB.latitude, "longitude": HB.longitude,
            "reason": "Cardiac arrest, CPR by bystander"}, BACKGROUND)
        self.assertEqual(pending["status"], "pending_approval")
        action = self.ctx.approvals.get(pending["action_id"])
        responder_ids = [r["unit_id"] for r in action.preview["responders"]]
        self.assertEqual(responder_ids, ["fr-01", "fr-02", "fr-04"])  # fr-03 too far, fr-05 busy
        self.assertTrue(all(self.ctx.world.find_unit(u).status == UnitStatus.AVAILABLE for u in responder_ids))
        self.ctx.approvals.approve(pending["action_id"], operator_id="op-17")
        self.assertTrue(all(self.ctx.world.find_unit(u).status == UnitStatus.ALERTED for u in responder_ids))

    def test_find_hospital_with_cath_lab(self):
        result = self.registry.execute("find_hospital", {"latitude": HB.latitude, "longitude": HB.longitude,
                                                         "capability": "cardiac_cath_lab"}, BACKGROUND)
        names = [h["name"] for h in result["hospitals"]]
        self.assertEqual(names[0], "Universitätsspital Zürich")
        self.assertNotIn("Stadtspital Zürich Waid", names)

    def test_handoff_and_notify(self):
        handoff = self.registry.execute("handoff_to_operator", {
            "reason": "Caller 079 384 19 28 panics", "urgency": "immediate", "incident_id": self.incident_id}, AgentRole.VOICE)
        self.assertNotIn("079 384 19 28", handoff["handoff"]["reason"])
        note = self.registry.execute("notify_centre", {
            "centre": "117", "incident_id": self.incident_id, "message": "Crowd at HB main hall"}, BACKGROUND)
        self.assertEqual(note["status"], "ok")
        self.assertEqual(len(self.ctx.world.centre_messages), 1)


class TestForestFireTools(unittest.TestCase):

    def setUp(self):
        self.ctx, self.registry = make_registry("forest_fire_uetliberg")
        result = self.registry.execute("update_incident", {
            "category": "wildfire", "description": "Forest fire on the west slope of the Uetliberg",
            "latitude": 47.3572, "longitude": 8.4852, "severity": 4,
            "call_ids": ["call-fire-001", "call-fire-002", "call-fire-003"]}, BACKGROUND)
        self.incident_id = result["incident"]["id"]
        spread = self.registry.execute("predict_spread", {"incident_id": self.incident_id}, BACKGROUND)
        self.forecasts = spread["forecasts"]
        self.spread = spread

    def test_related_reports_found(self):
        result = self.registry.execute("find_related_incidents", {"latitude": 47.3572, "longitude": 8.4852}, BACKGROUND)
        self.assertEqual([c["call_id"] for c in result["calls"]], ["call-fire-001", "call-fire-002", "call-fire-003"])
        self.assertEqual(len(result["social_posts"]), 2)
        all_text = " ".join(line for c in result["calls"] for line in c["transcript"])
        self.assertNotIn("044 461 22 87", all_text)

    def test_fire_data_and_weather(self):
        data = self.registry.execute("get_fire_data", {"latitude": 47.3572, "longitude": 8.4852}, BACKGROUND)
        self.assertEqual(data["hotspots"][0]["hotspot_id"], "hs-001")
        self.assertEqual(data["fire_danger_level"]["level"], 4)
        self.assertEqual({f["frame_id"] for f in data["frames"]}, {"frame-drone-1", "frame-tower-cam"})
        weather = self.registry.execute("get_weather", {"latitude": 47.3572, "longitude": 8.4852}, BACKGROUND)
        self.assertEqual(weather["downwind_bearing_deg"], 60.0)

    def test_scripted_frame_without_image(self):
        result = self.registry.execute("analyze_image", {"frame_id": "frame-drone-1", "question": "Where is the fire front?"}, BACKGROUND)
        self.assertEqual(result["method"], "scripted_simulation")
        self.assertIn("S10", result["observation"])

    def test_spread_grows_downwind(self):
        self.assertEqual(self.spread["ignition_source"], "satellite hotspots")
        heads = [f["head_distance_m"] for f in self.forecasts]
        self.assertEqual([f["horizon_minutes"] for f in self.forecasts], [60, 120, 180])
        self.assertEqual(heads, sorted(heads))
        polygon = self.ctx.forecasts[self.forecasts[-1]["forecast_id"]].polygon
        ignition = Coordinates(latitude=47.356, longitude=8.481)
        downwind = Coordinates(latitude=47.3605, longitude=8.4925)  # about 1 km to the east-north-east
        upwind = Coordinates(latitude=47.3515, longitude=8.4700)    # about 1 km to the west-south-west
        self.assertTrue(point_in_polygon(ignition, polygon))
        self.assertTrue(point_in_polygon(downwind, polygon))
        self.assertFalse(point_in_polygon(upwind, polygon))
        self.assertEqual(self.ctx.incidents[self.incident_id].hazard_polygon, polygon)

    def test_spread_refuses_non_wildfire(self):
        other = self.registry.execute("update_incident", {
            "category": "cardiac_arrest", "description": "x", "latitude": 47.35, "longitude": 8.49,
            "severity": 5, "call_ids": ["call-fire-003"]}, BACKGROUND)
        result = self.registry.execute("predict_spread", {"incident_id": other["incident"]["id"]}, BACKGROUND)
        self.assertIn("not a wildfire", result["error"])

    def test_exposure_grows_with_horizon(self):
        exposure = {f["horizon_minutes"]: self.registry.execute("estimate_exposure", {"forecast_id": f["forecast_id"]}, BACKGROUND)
                    for f in self.forecasts}
        inside_60 = {s["site_id"] for s in exposure[60]["sites_inside"]}
        inside_180 = {s["site_id"] for s in exposure[180]["sites_inside"]}
        self.assertEqual(inside_60, {"site-trail-north"})
        self.assertEqual(inside_180, {"site-trail-north", "site-forest-edge"})
        self.assertNotIn("site-uto-kulm", inside_180)
        assets = {a["asset_id"] for a in exposure[60]["infrastructure_crossing"]}
        self.assertIn("rail-s10-upper", assets)
        self.assertNotIn("rail-s10-lower", assets)
        self.assertEqual({t["train_id"] for t in exposure[60]["trains_at_risk"]}, {"train-s10-up", "train-s10-down"})

    def test_summit_route_avoids_fire_and_respects_capacity(self):
        forecast = self.ctx.forecasts[self.forecasts[-1]["forecast_id"]]
        result = self.registry.execute("plan_evacuation", {
            "incident_id": self.incident_id, "forecast_id": forecast.forecast_id,
            "start_latitude": UTO_KULM.latitude, "start_longitude": UTO_KULM.longitude, "people_count": 180}, BACKGROUND)
        route = result["route"]
        self.assertEqual(route["safe_destination_name"], "Assembly point Felsenegg (simulated)")
        rejected = {r["point_id"]: r["reason"] for r in result["rejected_assembly_points"]}
        self.assertEqual(rejected["ap-sellenbueren"], "capacity_too_small")
        self.assertEqual(rejected["ap-triemli"], "not_reachable")
        points = [Coordinates(**{k: w["coordinates"][k] for k in ("latitude", "longitude")}) for w in route["waypoints"]]
        for a, b in zip(points, points[1:]):
            self.assertFalse(segment_crosses_polygon(a, b, forecast.polygon))
        for point in points:
            self.assertGreaterEqual(distance_to_polygon_m(point, forecast.polygon), Config.EVACUATION_SAFETY_BUFFER_M)
        self.assertFalse(result["needs_fire_brigade_check"])

    def test_people_inside_fire_area_escape_without_going_downwind(self):
        forecast_id = self.forecasts[-1]["forecast_id"]
        result = self.registry.execute("plan_evacuation", {
            "incident_id": self.incident_id, "forecast_id": forecast_id,
            "start_latitude": 47.357, "start_longitude": 8.4845, "people_count": 25}, BACKGROUND)
        names = [w["name"] for w in result["route"]["waypoints"]]
        self.assertNotIn("Zürich Triemli station", names)  # the forest path to Triemli runs downwind through the fire
        self.assertTrue(result["needs_fire_brigade_check"])  # the escape climbs; the fire brigade must confirm it

    def test_infrastructure_and_alert_wait_for_approval(self):
        forecast_id = self.forecasts[-1]["forecast_id"]
        hold = self.registry.execute("request_infra_action", {
            "incident_id": self.incident_id, "asset_id": "rail-s10-upper", "action": "hold_trains",
            "reason": "Line crosses the predicted fire area within 60 min"}, BACKGROUND)
        wrong = self.registry.execute("request_infra_action", {
            "incident_id": self.incident_id, "asset_id": "rail-s10-upper", "action": "close_road", "reason": "x"}, BACKGROUND)
        self.assertIn("use 'hold_trains'", wrong["error"])
        no_german = self.registry.execute("draft_public_alert", {
            "incident_id": self.incident_id, "forecast_id": forecast_id, "alert_kind": "evacuate", "severity": 4,
            "area_description": "Uetliberg", "texts": [{"language": "en", "headline": "Fire", "instruction": "Leave"}],
            "reason": "x"}, BACKGROUND)
        self.assertIn("['de']", no_german["error"])
        alert = self.registry.execute("draft_public_alert", {
            "incident_id": self.incident_id, "forecast_id": forecast_id, "alert_kind": "evacuate", "severity": 4,
            "area_description": "Uetliberg summit and the forest north of it",
            "texts": [{"language": "de", "headline": "Waldbrand Uetliberg", "instruction": "Verlassen Sie den Gipfel Richtung Felsenegg."},
                      {"language": "en", "headline": "Forest fire Uetliberg", "instruction": "Leave the summit towards Felsenegg."}],
            "reason": "Fire forecast reaches the forest edge within 180 min"}, BACKGROUND)

        self.assertEqual(hold["status"], "pending_approval")
        self.assertEqual(alert["status"], "pending_approval")
        self.assertEqual(self.ctx.world.find_asset("rail-s10-upper").status, AssetStatus.NORMAL)
        self.assertTrue(all(t.status == TrainStatus.RUNNING for t in self.ctx.world.trains()))
        self.assertEqual(self.ctx.world.published_alerts, [])

        self.ctx.approvals.approve(hold["action_id"], operator_id="op-118")
        self.ctx.approvals.approve(alert["action_id"], operator_id="op-118")
        self.assertEqual(self.ctx.world.find_asset("rail-s10-upper").status, AssetStatus.TRAINS_HELD)
        self.assertTrue(all(t.status == TrainStatus.HELD for t in self.ctx.world.trains()))
        self.assertEqual(len(self.ctx.world.published_alerts), 1)
        self.assertEqual(self.ctx.incidents[self.incident_id].status, IncidentStatus.EVACUATING)

    def test_route_card_is_drawn_by_code(self):
        forecast_id = self.forecasts[-1]["forecast_id"]
        route = self.registry.execute("plan_evacuation", {
            "incident_id": self.incident_id, "forecast_id": forecast_id,
            "start_latitude": UTO_KULM.latitude, "start_longitude": UTO_KULM.longitude, "people_count": 180}, BACKGROUND)
        with tempfile.TemporaryDirectory() as folder:
            original = Config.ARTIFACT_DIR
            Config.ARTIFACT_DIR = Path(folder)
            try:
                card = self.registry.execute("make_route_card", {"route_id": route["route"]["route_id"], "language": "de"}, BACKGROUND)
                path = Path(card["artifact"]["media_url"].replace("file://", ""))
                svg = path.read_text(encoding="utf-8")
            finally:
                Config.ARTIFACT_DIR = original
        self.assertEqual(card["artifact"]["artifact_type"], "route_card_svg")
        self.assertIn("Evakuierungsroute", svg)
        self.assertIn("Felsenegg", svg)
        self.assertIn("<polygon", svg)


class TestHelpers(unittest.TestCase):

    def test_scrub_pii(self):
        text = "Ich bin Thomas, Nummer 079 384 19 28, oder +41 79 384 19 28, mail t.b@example.ch, AHV 756.1234.5678.97"
        clean = scrub_pii(text)
        for secret in ("079 384 19 28", "+41 79 384 19 28", "t.b@example.ch", "756.1234.5678.97"):
            self.assertNotIn(secret, clean)
        self.assertIn("Thomas", clean)  # a single first name is not detected (documented limit)

    def test_scrub_pii_removes_self_introduced_names(self):
        self.assertEqual(scrub_pii("Hier ist Sandra Keller vom Hotel Uto Kulm."), "Hier ist [name removed] vom Hotel Uto Kulm.")
        self.assertEqual(scrub_pii("Ich bin Thomas Brunner, bitte schnell."), "Ich bin [name removed], bitte schnell.")
        self.assertEqual(scrub_pii("Ich bin Arzt und helfe."), "Ich bin Arzt und helfe.")
        self.assertEqual(scrub_pii("This is Zürich HB main hall."), "This is Zürich HB main hall.")

    def test_scrub_pii_keeps_coordinates_times_and_counts(self):
        text = "47.37795, 8.54025 at 2026-08-14 16:20 with 180 guests"
        self.assertEqual(scrub_pii(text), text)

    def test_haversine(self):
        self.assertAlmostEqual(haversine_m(HB, UTO_KULM), 5000, delta=300)


if __name__ == "__main__":
    unittest.main()
