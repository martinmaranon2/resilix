"""
Unit tests for the link between operator approvals and the voice call (no network).
"""

import asyncio
import logging
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from alpineguard.agents.incident_coordinator import IncidentCoordinator, describe_approved_action
from alpineguard.models.tooling import AgentRole
from alpineguard.simulation.world import SimulatedWorld
from alpineguard.tools.context import ToolContext
from alpineguard.tools.registry import build_registry

logging.getLogger("alpineguard").setLevel(logging.WARNING)


class FakeCall:
    """Stands in for VoiceCallSession: records pushed updates."""

    def __init__(self, call_id):
        self.call_id = call_id
        self.updates = []

    async def push_update(self, text):
        self.updates.append(text)


class TestCoordination(unittest.TestCase):

    def setUp(self):
        self.ctx = ToolContext.for_world(SimulatedWorld.load("cardiac_arrest_zurich_hb"))
        self.registry = build_registry(self.ctx)
        self.card = {"category": "cardiac_arrest", "description": "Man collapsed", "latitude": 47.37795,
                     "longitude": 8.54025, "severity": 5, "call_ids": ["call-hb-001"]}

    def test_one_incident_per_call(self):
        first = self.registry.execute("update_incident", self.card, AgentRole.VOICE)
        second = self.registry.execute("update_incident", {**self.card, "description": "Gasping"}, AgentRole.BACKGROUND)
        self.assertEqual(first["incident"]["id"], second["incident"]["id"])
        self.assertEqual(len(self.ctx.incidents), 1)
        self.assertEqual(second["incident"]["description"], "Gasping")

    def test_only_approved_actions_reach_the_call(self):
        call = FakeCall("call-hb-001")
        coordinator = IncidentCoordinator(self.registry, call, background=object())
        incident_id = self.registry.execute("update_incident", self.card, AgentRole.VOICE)["incident"]["id"]
        approved = self.registry.execute("propose_dispatch", {"incident_id": incident_id, "unit_ids": ["amb-11"],
                                                              "priority": "P1", "reason": "x"}, AgentRole.BACKGROUND)
        rejected = self.registry.execute("propose_dispatch", {"incident_id": incident_id, "unit_ids": ["amb-23"],
                                                              "priority": "P1", "reason": "x"}, AgentRole.BACKGROUND)
        self.assertEqual(asyncio.run(coordinator.deliver_updates()), 0)  # nothing before a decision
        self.ctx.approvals.approve(approved["action_id"], operator_id="op-17")
        self.ctx.approvals.reject(rejected["action_id"], operator_id="op-17")
        self.assertEqual(asyncio.run(coordinator.deliver_updates()), 1)
        self.assertIn("SRZ ambulance 11", call.updates[0])
        self.assertIn("about 3 min", call.updates[0])
        self.assertNotIn("ambulance 23", call.updates[0])

    def test_describe_approved_action_lists_etas(self):
        incident_id = self.registry.execute("update_incident", self.card, AgentRole.VOICE)["incident"]["id"]
        pending = self.registry.execute("alert_first_responders", {"incident_id": incident_id, "latitude": 47.37795,
                                                                   "longitude": 8.54025, "reason": "x"}, AgentRole.BACKGROUND)
        action = self.ctx.approvals.approve(pending["action_id"], operator_id="op-17")
        text = describe_approved_action(action)
        self.assertTrue(text.startswith("The operator approved:"))
        self.assertIn("First responder volunteer 1 (simulated) about", text)


if __name__ == "__main__":
    unittest.main()
