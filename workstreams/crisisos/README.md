> This version is included in the consolidated project. See the repository-root README for the current folder layout and primary run commands. Run version-specific commands from this folder.

# CrisisOS Switzerland — Disaster Data Integrations

A Python data-integration layer for Swiss disaster intelligence, developed on the `swiss-disaster-data-integrations-12-sources` branch. It combines weather, river measurements, webcams, terrain, hazards, transport, infrastructure, earthquakes, and building-exposure information behind reusable tool functions.

This branch is the work proposed in [PR #3](https://github.com/ixsanpe/hackathon-tech-europe/pull/3). The default branch separately contains the AlpineGuard simulation. Keep the two implementations distinct when reviewing features and run instructions.

## Architecture

Provider HTTP clients → normalized models and source-specific responses → exported functions in `crisis_data.agent_tools` → downstream reasoning or monitoring code.

`crisis_data/config.py` centralizes endpoints, geographic defaults, timeout settings, and environment-based credentials. `logger.py` supplies function-call logging; `health.py` checks provider status. The integration layer exposes tools intended for a Gemini agent, but does not itself implement a complete Gemini/Gradium application, dispatcher service, or frontend.

## Implemented integration areas

| Area                                   | Modules in `crisis_data/`                  |
| -------------------------------------- | ------------------------------------------ |
| Weather forecasts                      | `open_meteo.py`                            |
| River stations and measurements        | `bafu_hydro.py`                            |
| Webcam metadata and image retrieval    | `windy_webcams.py`                         |
| Elevation and coordinate conversion    | `swisstopo.py`                             |
| Ground observations and radar metadata | `meteoswiss_smn.py`, `meteoswiss_radar.py` |
| Nearby infrastructure                  | `osm_infrastructure.py`                    |
| Road incidents                         | `astra_traffic.py`                         |
| Flood zones and hazard warnings        | `flood_hazard.py`, `hazard_warnings.py`    |
| Earthquakes                            | `sed_earthquakes.py`                       |
| Building and population exposure       | `bfs_population.py`                        |

These are implemented clients, not a guarantee of current provider availability or complete data. Some paths return simulated fallback records or empty/error results when credentials or upstream services are unavailable. Check response status, source, timestamps, and simulation flags before using the data.

## Setup

The implementation uses Python 3.9+ standard-library features plus `requests` and `python-dotenv`. A modern Python build with supported OpenSSL is preferable for HTTPS providers.

```sh
git clone --branch swiss-disaster-data-integrations-12-sources https://github.com/martinmaranon2/hackathon-tech-europe.git
cd hackathon-tech-europe
python3 -m venv .venv
.venv/bin/python -m pip install requests python-dotenv
cp .env.example .env
```

The branch does not include a dependency manifest or lockfile. The audit used requests 2.32.5 and python-dotenv 1.2.1; the command above resolves available versions.

Configure only the credentials needed in the ignored `.env`:

| Variable         | Purpose                                                                                 |
| ---------------- | --------------------------------------------------------------------------------------- |
| `WINDY_API_KEY`  | Authenticated webcam access                                                             |
| `OTD_API_KEY`    | Authenticated road-traffic feed                                                         |
| `GEMINI_API_KEY` | Reserved for downstream Gemini usage; importing these data tools does not invoke Gemini |
| `LOG_LEVEL`      | Logging level                                                                           |

The template also lists `CRISIS_HTTP_TIMEOUT`; inspect `config.py` for the per-provider timeout constants actually used. Do not commit real credentials or copy request logs containing sensitive information into documentation.

## Run and verify

Import the tool interface without calling live providers:

```sh
.venv/bin/python -c "import crisis_data.agent_tools; print('Tool imports OK')"
```

Run the retained AlpineGuard simulation tests:

```sh
.venv/bin/python -m unittest discover -s tests -v
```

To exercise the external data integrations explicitly:

```sh
.venv/bin/python test_integrations.py
```

The last command makes live HTTP requests and may require provider credentials. It runs source checks and then a health pass, so it can make multiple requests per provider. Its current exit code accepts at least 11 successful checks out of 12; inspect the individual results rather than treating exit zero as proof that all sources passed.

Audit on 2026-10-22: environment creation, installation, all tool imports, an offline WGS84/LV95 coordinate round-trip, and the three existing simulation tests passed on Python 3.9.6. That Python build emitted an urllib3/LibreSSL compatibility warning. Live provider checks and model calls were not run. The existing historical source-health tables were not revalidated.

## Documentation and collaboration

- [Design](Design.md): architecture and feature map; distinguish implemented data clients from proposed agent/UI integrations.
- [Data sources](DATA_SOURCES.md) and [module guide](crisis_data/README.md): provider details and examples.
- [Broader emergency-assistant proposal](docs/architecture-emergency-assistant.md): overall vision.
- [AGENTS.md](AGENTS.md): contribution conventions and Entire workflow.

Use branches and pull requests; do not merge or overwrite the existing contribution branch without review.

This personal fork preserves the shared source and its contributor history: [ixsanpe/hackathon-tech-europe](https://github.com/ixsanpe/hackathon-tech-europe).

## Project history and final integrated application

Martin clarified that the Tech Europe hackathon repositories were individual workstreams that one teammate later combined into the final public project: [Resilix](https://github.com/20261010-hack-CH-ZH-ZRH-AgenticAI/resilix-web).

This README describes the preserved workstream in this branch. Its scope and verification limits apply to this version, not to the final integrated Resilix application. Use the final repository for the combined project's setup and product documentation.
