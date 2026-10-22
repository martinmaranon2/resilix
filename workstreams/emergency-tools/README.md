# Emergency tools and agents workstream

This folder preserves `feat/emergency-tools` from the original Tech Europe repository (commit `043ef59efeda830c366dca3a91cbc46d150575b5`). It contains the simulated world, emergency protocols and tools, background/voice agents, coordinator, approval queue, audit records and scenario tests developed before the final Resilix application was assembled.

## Run local tests

From this folder, using Python 3:

```sh
python3 -m unittest discover -s tests -v
```

The consolidation check ran 44 tests: 41 passed and three credential-gated Gemini tests were skipped. The ordinary tests do not require model credentials. Live agent demos additionally require the `google-genai` package and `GEMINI_API_KEY`; provider names and model IDs are the original source configuration and were not validated against live services in this audit.

## Architecture

`simulation/world.py` loads scenarios; `tools/registry.py` exposes the emergency tools through shared context. Tool calls are subject to roles and approval tiers. `agents/background_agent.py` and `agents/voice_agent.py` implement the model-facing loops; `agents/incident_coordinator.py` connects a call with background work and approved-action updates. `config.py` centralizes scenario paths and model/tool settings.

This is Python domain and agent logic. No HTTP server implementing the final Resilix web app's authentication, session, and API contract was found in this branch. See the repository-root README for the final web app and integration boundary.

Original source history for this and all other original branches is restorable from `../../history/tech-europe-workstreams.bundle`; exact sources are listed in `../../SOURCES.json`.
