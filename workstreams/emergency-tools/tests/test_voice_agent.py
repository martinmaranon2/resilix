"""
Tests for the voice agent.

Unit test (no network): tool calls from the Live API run through the registry with role VOICE.
End-to-end test (Gemini Live, opt-in with ALPINEGUARD_RUN_E2E=1 and GEMINI_API_KEY): a scripted
cardiac arrest call; the agent must locate the caller, read the protocol and answer every turn.
"""

import asyncio
import logging
import os
import sys
import unittest
from types import SimpleNamespace

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from alpineguard.agents.voice_agent import VoiceCallSession, answer_tool_calls
from alpineguard.simulation.world import SimulatedWorld
from alpineguard.tools.context import ToolContext
from alpineguard.tools.registry import build_registry

logging.getLogger("alpineguard").setLevel(logging.WARNING)
RUN_E2E = os.environ.get("ALPINEGUARD_RUN_E2E") == "1" and bool(os.environ.get("GEMINI_API_KEY"))


class TestVoiceToolCalls(unittest.TestCase):

    def test_voice_role_is_enforced(self):
        ctx = ToolContext.for_world(SimulatedWorld.load("cardiac_arrest_zurich_hb"))
        registry = build_registry(ctx)
        calls = [
            SimpleNamespace(id="c1", name="locate_caller", args={"call_id": "call-hb-001"}),
            SimpleNamespace(id="c2", name="propose_dispatch", args={"incident_id": "x", "unit_ids": ["amb-11"], "priority": "P1", "reason": "x"}),
        ]
        answers = answer_tool_calls(registry, calls)
        self.assertEqual([a["id"] for a in answers], ["c1", "c2"])
        self.assertEqual(answers[0]["response"]["status"], "ok")
        self.assertIn("not available to the voice agent", answers[1]["response"]["error"])
        self.assertEqual(ctx.approvals.all(), [])
        self.assertEqual(ctx.audit.entries()[0].actor, "voice_agent")


@unittest.skipUnless(RUN_E2E, "set ALPINEGUARD_RUN_E2E=1 and GEMINI_API_KEY to run the Gemini Live test")
class TestVoiceAgentWithGeminiLive(unittest.TestCase):

    def test_cardiac_arrest_call(self):
        world = SimulatedWorld.load("cardiac_arrest_zurich_hb")
        ctx = ToolContext.for_world(world)
        registry = build_registry(ctx)

        async def play():
            async with VoiceCallSession(registry, "call-hb-001") as call:
                for step in world.voice_script[:3]:
                    await call.say(step["text"])
                return call.turns

        turns = asyncio.run(play())
        used = {name for t in turns for name in t.tool_calls}
        self.assertIn("locate_caller", used)
        self.assertIn("get_protocol", used)
        self.assertTrue(all(t.agent_text.strip() for t in turns))
        self.assertEqual(ctx.approvals.all(), [])


if __name__ == "__main__":
    unittest.main()
