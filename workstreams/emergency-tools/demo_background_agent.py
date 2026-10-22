"""
Demo: the Gemini background agent prepares an incident, then the operator decides.

Architecture
------------
1. Load a scenario into the simulated world (cardiac arrest at Zürich HB, or forest fire
   on the Uetliberg).
2. Build the task from the scenario's trigger calls (phone numbers removed).
3. Run the background agent (Gemini function calling over the tool registry).
4. Show the tool calls, the agent's summary and the pending approvals.
5. Let the operator decide: approve all, reject all, or ask per action.
6. Show what changed in the world, and write a JSON run report next to the artifacts.

Use cases
---------
    python demo_background_agent.py --scenario cardiac_arrest_zurich_hb
    python demo_background_agent.py --scenario forest_fire_uetliberg --decide ask
Needs GEMINI_API_KEY in the environment.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "src")))

from alpineguard import BackgroundIncidentAgent, SimulatedWorld, ToolContext, build_incident_task, build_registry
from alpineguard.config import Config
from alpineguard.models.agent_runs import AgentStopReason
from alpineguard.tools.vision import GeminiVisionAnalyzer


def parse_args() -> argparse.Namespace:
    """
    Read command line options.

    Returns:
        Parsed options.
    """
    parser = argparse.ArgumentParser(description="Run the AlpineGuard background agent on a demo scenario.")
    parser.add_argument("--scenario", choices=SimulatedWorld.available_scenarios(), default="cardiac_arrest_zurich_hb")
    parser.add_argument("--decide", choices=["approve", "reject", "ask"], default="approve",
                        help="Operator decision for all pending actions (default: approve).")
    parser.add_argument("--operator", default="demo-operator", help="Operator id written to the audit trail.")
    return parser.parse_args()


def main() -> int:
    """
    Run the demo.

    Returns:
        Process exit code: 0 when the agent finished, 1 otherwise.
    """
    args = parse_args()
    world = SimulatedWorld.load(args.scenario)
    ctx = ToolContext.for_world(world, vision=GeminiVisionAnalyzer())
    registry = build_registry(ctx)
    ctx.vision._audit = ctx.audit
    agent = BackgroundIncidentAgent(registry)
    task = build_incident_task(world, world.trigger_call_ids)

    print("=" * 80)
    print(f"SCENARIO: {world.title}  (model: {agent.model})")
    print(f"Data: {world.data_note}")
    print("=" * 80)
    print(task)

    result = agent.run(task)

    print("\n" + "-" * 80)
    print(f"[TOOL CALLS] {len(result.tool_calls)} calls in {result.turns} turns, stop reason: {result.stop_reason.value}")
    for call in result.tool_calls:
        action = f" -> {call.action_id}" if call.action_id else ""
        print(f"  turn {call.turn:2d}  {call.name:24s} {call.status}{action}")
    if result.error:
        print(f"  ERROR: {result.error}")

    print("\n" + "-" * 80)
    print("[AGENT SUMMARY FOR THE OPERATOR]")
    print(result.final_text or "(no summary)")

    print("\n" + "-" * 80)
    print("[PENDING APPROVALS]")
    for action in ctx.approvals.pending():
        print(f"  {action.action_id}  {action.tool_name.value}")
        print(f"    Summary: {action.summary}")
        print(f"    Reason:  {action.reason}")

    print("\n" + "-" * 80)
    print(f"[OPERATOR DECISIONS] mode: {args.decide}, operator: {args.operator}")
    for action in ctx.approvals.pending():
        decision = args.decide
        if decision == "ask":
            answer = input(f"  Approve {action.action_id} ({action.summary})? [y/N] ").strip().lower()
            decision = "approve" if answer == "y" else "reject"
        if decision == "approve":
            decided = ctx.approvals.approve(action.action_id, operator_id=args.operator)
        else:
            decided = ctx.approvals.reject(action.action_id, operator_id=args.operator, note="Rejected in demo")
        print(f"  {decided.action_id}: {decided.status.value} {decided.result or decided.error or ''}")

    print("\n" + "-" * 80)
    print("[WORLD AFTER THE DECISIONS]")
    for unit in world.units():
        if unit.assigned_incident_id:
            print(f"  unit {unit.unit_id}: {unit.status.value} -> {unit.assigned_incident_id}")
    for asset in world.assets():
        print(f"  asset {asset.asset_id}: {asset.status.value}")
    for train in world.trains():
        print(f"  train {train.train_id}: {train.status.value}")
    for alert in world.published_alerts:
        print(f"  published alert {alert.alert_id}: {alert.texts[0].headline}")
    for incident in ctx.incidents.values():
        print(f"  incident {incident.id}: {incident.category.value}, status {incident.status.value}, "
              f"severity {incident.severity.value}, calls {incident.call_ids}")
    for artifact in ctx.artifacts.values():
        print(f"  artifact {artifact.artifact_type.value}: {artifact.media_url}")

    Config.ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = Config.ARTIFACT_DIR / f"run-{world.scenario_id}.json"
    report = {
        "scenario_id": world.scenario_id,
        "agent_run": result.to_dict(),
        "incidents": [i.to_dict() for i in ctx.incidents.values()],
        "actions": [a.to_dict() for a in ctx.approvals.all()],
        "audit": [e.to_dict() for e in ctx.audit.entries()],
    }
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"\nRun report: {report_path}")
    return 0 if result.stop_reason == AgentStopReason.FINISHED else 1


if __name__ == "__main__":
    sys.exit(main())
