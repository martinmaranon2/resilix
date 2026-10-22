# AlpineGuard implementation design

This document describes the source currently present on the default branch. The wider system proposal remains in [docs/architecture-emergency-assistant.md](docs/architecture-emergency-assistant.md).

## Runtime flow

`demo_simulation.py` → `SupervisorDispatcherAgent.process_emergency_signal` → avalanche assessment → evacuation planning → multimodal artifact records → civilian and dispatcher summaries.

| Feature               | Implementation                               | Relationship and current scope                                                       |
| --------------------- | -------------------------------------------- | ------------------------------------------------------------------------------------ |
| Incident triage       | `src/alpineguard/agents/supervisor_agent.py` | Creates incident state and coordinates the remaining stages                          |
| Avalanche assessment  | `src/alpineguard/agents/avalanche_agent.py`  | Consumes connector responses and produces severity and a hazard polygon              |
| Environmental sources | `src/alpineguard/connectors/swiss_data.py`   | Returns simulated bulletin, webcam, and terrain records                              |
| Evacuation planning   | `src/alpineguard/agents/evacuation_agent.py` | Builds scenario-specific route/waypoint data and requests map/video artifact records |
| Multimodal artifacts  | `src/alpineguard/models/multimodal.py`       | Constructs an SVG preview, prompts, metadata, and placeholder CDN URLs               |
| Domain contracts      | `src/alpineguard/models/domain.py`           | Shared dataclasses and enums for incidents, routes, and artifacts                    |
| Console demonstration | `demo_simulation.py`                         | Prints the end-to-end response                                                       |
| Verification          | `tests/test_agents.py`                       | Covers surveillance, evacuation artifacts, and supervisor dispatch output            |

## State and external effects

Runtime state is held in Python objects. UUIDs distinguish generated incidents and artifacts. There is no configured persistence layer, live data transport, real dispatch action, or media upload in this simulation. The civilian PWA and dispatcher console are represented by dictionaries in the supervisor response rather than deployed interfaces.

## Planned integration boundaries

The broader proposal names live Swiss environmental feeds, voice intake, model-based media generation, and operator interfaces. These require real clients, configuration, failure handling, and validation before being represented as implemented features. Keep provider credentials outside source control. When those features are added, update this map and the README to distinguish tested behavior from plans.

## Verification

From the repository root:

```sh
python3 demo_simulation.py
python3 -m unittest discover -s tests -v
```

Both commands passed during the 2026-10-22 documentation audit. No runtime behavior was changed.
