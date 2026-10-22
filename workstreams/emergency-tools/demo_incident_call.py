"""
Demo: voice agent, background agent and operator work on one cardiac arrest call.

Architecture
------------
1. The voice agent answers the first caller line and creates the incident card.
2. The coordinator starts the background agent in the background.
3. A simulated operator approves every pending action after a short delay
   (``--operator-delay``); this stands in for clicks on the operator console.
4. Between caller lines, approved actions are pushed into the call, so the voice
   agent tells the caller what is coming.

Use cases
---------
    python demo_incident_call.py
Needs GEMINI_API_KEY in the environment.
"""

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "src")))

from alpineguard import SimulatedWorld, ToolContext, build_registry
from alpineguard.agents.incident_coordinator import IncidentCoordinator
from alpineguard.agents.voice_agent import VoiceCallSession


async def simulated_operator(ctx: ToolContext, coordinator: IncidentCoordinator, delay_s: float) -> None:
    """
    Approve each pending action after a delay, while the background agent works.

    Parameters:
        ctx: Tool context with the approval queue.
        coordinator: Coordinator (to know when the background agent is done).
        delay_s: Seconds between seeing an action and approving it.
    """
    seen = set()
    while coordinator.background_running or ctx.approvals.pending():
        for action in ctx.approvals.pending():
            if action.action_id in seen:
                continue
            seen.add(action.action_id)
            await asyncio.sleep(delay_s)
            decided = ctx.approvals.approve(action.action_id, operator_id="demo-operator")
            print(f"\n  [OPERATOR] approved {action.tool_name.value}: {decided.status.value}")
        await asyncio.sleep(0.5)


async def run(delay_s: float) -> int:
    """
    Play the cardiac arrest call with all three roles.

    Parameters:
        delay_s: Simulated operator delay per action.

    Returns:
        Process exit code: 0 when at least one approval reached the caller.
    """
    world = SimulatedWorld.load("cardiac_arrest_zurich_hb")
    ctx = ToolContext.for_world(world)
    registry = build_registry(ctx)
    caller_lines = [s["text"] for s in world.voice_script if s["speaker"] == "caller"]

    async with VoiceCallSession(registry, world.trigger_call_ids[0]) as call:
        coordinator = IncidentCoordinator(registry, call)
        print(f"CALLER: {caller_lines[0]}")
        print(f"AGENT:  {(await call.say(caller_lines[0])).agent_text.strip()}")
        coordinator.start_background()
        print(f"\n  [BACKGROUND] started (incident so far: {coordinator.incident_id})")
        operator = asyncio.create_task(simulated_operator(ctx, coordinator, delay_s))

        for line in caller_lines[1:]:
            print(f"\nCALLER: {line}")
            print(f"AGENT:  {(await call.say(line)).agent_text.strip()}")
            delivered = await coordinator.deliver_updates()
            for turn in call.turns[len(call.turns) - delivered:] if delivered else []:
                print(f"  [SYSTEM UPDATE -> CALL] {turn.caller_text}")
                print(f"AGENT:  {turn.agent_text.strip()}")

        await coordinator.wait_for_background()
        await operator
        delivered = await coordinator.deliver_updates()
        for turn in call.turns[len(call.turns) - delivered:] if delivered else []:
            print(f"\n  [SYSTEM UPDATE -> CALL] {turn.caller_text}")
            print(f"AGENT:  {turn.agent_text.strip()}")

    print("\n" + "-" * 80)
    print(f"Incidents: {[(i.id, i.status.value) for i in ctx.incidents.values()]}")
    print(f"Updates delivered to the call: {len(coordinator.delivered)}")
    return 0 if coordinator.delivered and len(ctx.incidents) == 1 else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Voice agent + background agent + simulated operator on one call.")
    parser.add_argument("--operator-delay", type=float, default=3.0)
    sys.exit(asyncio.run(run(parser.parse_args().operator_delay)))
