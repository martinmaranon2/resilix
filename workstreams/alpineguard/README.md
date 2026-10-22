> This version is included in the consolidated project. See the repository-root README for the current folder layout and primary run commands. Run version-specific commands from this folder.

# AlpineGuard — Swiss Emergency Response Simulation

A Python hackathon prototype that simulates an alpine emergency workflow: receive a distress signal, assess avalanche risk, plan an evacuation, and produce separate guidance for civilians and dispatchers.

**Current implementation:** the checked-in demo uses simulated Swiss environmental data, fixed routing logic, and generated artifact metadata. It does not contact emergency services, fetch live SLF/MeteoSwiss feeds, or call the named media-generation models. Use it to demonstrate software orchestration, not to make real emergency decisions.

## How it works

1. `SupervisorDispatcherAgent` creates and triages an incident.
2. `AvalancheSurveillanceAgent` combines simulated bulletin, webcam, and terrain data into a hazard assessment.
3. `EvacuationRouteAgent` returns a route and waypoints for the demo scenario.
4. `MultimodalGenerationPipeline` constructs an inline SVG preview plus map, video, and landing-zone artifact records.
5. The supervisor returns structured civilian guidance, dispatcher information, and an action log.

Media URLs are constructed demo strings; the code does not upload files or render the referenced videos/images.

## Tech stack

Python standard library: dataclasses, enums, typing, UUIDs, and unittest. The current simulation needs no third-party packages or API keys. Entire is used for development history and workflow integration, not for running the demo.

## Project layout

| Path                                       | Responsibility                                        |
| ------------------------------------------ | ----------------------------------------------------- |
| `demo_simulation.py`                       | Console demonstration                                 |
| `src/alpineguard/agents/`                  | Supervisor, avalanche, and evacuation agents          |
| `src/alpineguard/connectors/swiss_data.py` | Simulated environmental connector responses           |
| `src/alpineguard/models/domain.py`         | Incident, route, coordinate, and artifact data models |
| `src/alpineguard/models/multimodal.py`     | SVG preview and placeholder artifact construction     |
| `tests/test_agents.py`                     | Three agent and orchestration tests                   |
| `Design.md`                                | Implementation map and planned integration boundaries |
| `docs/`                                    | Broader architecture proposal                         |

## Setup and run

Use Python 3; the audit ran with Python 3.9.6. A virtual environment is optional because there are no external dependencies.

```sh
git clone https://github.com/martinmaranon2/hackathon-tech-europe.git
cd hackathon-tech-europe
python3 demo_simulation.py
```

The demo prints a Furka Pass incident, a hazard assessment, an evacuation route, three artifact records, and dispatcher guidance. IDs vary between runs.

## Tests

Run from the repository root:

```sh
python3 -m unittest discover -s tests -v
```

Audit on 2026-10-22: the demonstration completed and all three existing tests passed. These tests exercise the simulated implementation; they do not validate real-world route safety or external integrations.

## Design and development context

[Design.md](Design.md) maps implemented features to source files. The [architecture proposal](docs/architecture-emergency-assistant.md), [Gradium setup notes](GRADIUM_SETUP.md), and [Entire setup](ENTIRE_SETUP.md) describe additional plans and tooling; they are not proof of implemented runtime integrations.

The original project also links an [architecture diagram](https://drive.google.com/file/d/1DTmGxwnCslS5hmaFK8Z8PrWeHEGtHJpX/view?usp=drive_link). Its contents were not used to infer current code behavior.

Follow [AGENTS.md](AGENTS.md) and the repository's Entire guide for contributions. Keep shared work in reviewable branches and pull requests.

This personal fork preserves the shared source and its contributor history: [ixsanpe/hackathon-tech-europe](https://github.com/ixsanpe/hackathon-tech-europe).

The separate CrisisOS data-integration implementation is preserved on the `swiss-disaster-data-integrations-12-sources` branch. See its branch README for setup and provider integration details.

## Project history and final integrated application

Martin clarified that the Tech Europe hackathon repositories were individual workstreams that one teammate later combined into the final public project: [Resilix](https://github.com/20261010-hack-CH-ZH-ZRH-AgenticAI/resilix-web).

This README describes the preserved workstream in this branch. Its scope and verification limits apply to this version, not to the final integrated Resilix application. Use the final repository for the combined project's setup and product documentation.
