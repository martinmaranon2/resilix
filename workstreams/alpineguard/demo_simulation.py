import sys
import os
import json

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "src")))

from alpineguard import (
    SupervisorDispatcherAgent, IncidentCategory, Coordinates
)

def run_simulation():
    print("=" * 80)
    print("ALPINEGUARD: AUTONOMOUS EMERGENCY DISPATCH SIMULATION (SWITZERLAND)")
    print("=" * 80)

    supervisor = SupervisorDispatcherAgent()

    # Scenario: Alpine distress at Furka Pass
    caller_coords = Coordinates(latitude=46.5584, longitude=8.5612, altitude_m=2436.0)
    print(f"\n[INCOMING DISTRESS SIGNAL 112]")
    print(f"Caller: +41 79 384 19 28 (Furka Pass, Canton Uri)")
    print(f"Coordinates: {caller_coords.latitude}, {caller_coords.longitude} (Alt: {caller_coords.altitude_m}m)")
    print(f"Message: 'Slab avalanche broke loose above us on North slope. 3 ski tourers safe on ridge, but descent to road blocked.'")

    result = supervisor.process_emergency_signal(
        caller_id="+41793841928",
        category=IncidentCategory.AVALANCHE,
        canton="UR",
        location="Furka Pass Ridge",
        coordinates=caller_coords,
        raw_distress_text="Slab avalanche broke loose above us on North slope. 3 ski tourers safe on ridge, but descent to road blocked."
    )

    incident = result["incident"]
    route = result["evacuation_route"]
    artifacts = result["multimodal_artifacts"]
    summary = result["action_summary"]

    print("\n" + "-" * 50)
    print("[SUPERVISOR AGENT AUDIT LOG]")
    for log_entry in result["supervisor_action_log"]:
        print(f"  {log_entry}")

    print("\n" + "-" * 50)
    print(f"[TRIAGE & STATUS] Incident ID: {incident.id}")
    print(f"Status: {incident.status.value.upper()} | Severity: {incident.severity.name}")

    print("\n" + "-" * 50)
    print(f"[DYNAMIC EVACUATION ROUTE]")
    print(f"Destination: {route.safe_destination_name}")
    print(f"Distance: {route.total_distance_km} km | Est. Walk Time: {route.estimated_walking_time_mins} mins")
    print(f"Elevation Profile Drop: {route.elevation_drop_m} m")
    print("\nWaypoints:")
    for idx, wp in enumerate(route.waypoints, 1):
        print(f"  {idx}. {wp.name} [ETA: +{wp.eta_minutes}m] - Clearance: {wp.hazard_clearance_m}m")
        print(f"     Guidance: {wp.instruction}")

    print("\n" + "-" * 50)
    print("[PHASE 3 MULTIMODAL GENERATIVE ARTIFACTS]")
    for art in artifacts:
        print(f"  • Type: {art.artifact_type.upper()}")
        print(f"    URL: {art.media_url}")
        print(f"    Prompt/Spec: {art.prompt[:90]}...")
        if "svg_preview" in art.metadata:
            print(f"    Preview: Embedded vector SVG ready for offline PWA cache")

    print("\n" + "-" * 50)
    print("[FIRST RESPONDERS DISPATCH (112 / REGA)]")
    print(f"Units Alerted: {', '.join(summary['dispatcher_112_console']['recommended_unit_dispatch'])}")
    print(f"Rega LZ Tactical Briefing: {summary['dispatcher_112_console']['rega_lz_briefing_url']}")
    print("=" * 80)
    print("SIMULATION COMPLETED SUCCESSFULLY")

if __name__ == "__main__":
    run_simulation()
