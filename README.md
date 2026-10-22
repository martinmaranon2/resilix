# Resilix — Agentic Disaster Awareness

One project repository containing the final integrated Resilix web application and the original Tech Europe development workstreams. The team combined the individual workstreams into [the final public app](https://github.com/20261010-hack-CH-ZH-ZRH-AgenticAI/resilix-web); this fork keeps that application and the earlier contribution evidence together.

## Repository layout

| Path | What it contains |
| --- | --- |
| Repository root (`src/`, `public/`, `vendor/`) | Final integrated Bun/Next.js web app; run the web commands below from this root |
| `workstreams/crisisos/` | Martin's Swiss data-integration workstream, including provider clients, models, tools, design notes and smoke runner |
| `workstreams/alpineguard/` | Earlier Python emergency-response simulation |
| `workstreams/emergency-tools/` | Python emergency tools, background/voice agent logic, simulated world, approval flow and scenario tests |
| `history/` | Restorable Git history for the original workstreams and their exact source references |
| `SOURCES.json` | Original repositories, branches, commit IDs and folder mappings |

The workstreams are preserved development versions. They are not automatically substituted for the final application's backend. The web app requires a compatible HTTP/WebSocket backend at `API_BASE_URL`. All ten original Tech Europe branches were checked: the emergency-tools branch contains Python agents and tool logic, now included here, but no server implementing the final web app's authentication/session and API contracts was found. The public organization exposes only `resilix-web`; do not assume the earlier agent scripts are a drop-in HTTP backend.

### Earlier workstream commands

```sh
# From this repository's root; Python standard library only.
python3 workstreams/alpineguard/demo_simulation.py
python3 -m unittest discover -s workstreams/alpineguard/tests -v

# Run the CrisisOS workstream separately.
cd workstreams/crisisos
python3 -m venv .venv
.venv/bin/python -m pip install requests python-dotenv
.venv/bin/python -c "import crisis_data.agent_tools; print('Tool imports OK')"
```

Live CrisisOS provider checks are optional and make network requests: run `.venv/bin/python test_integrations.py` from that workstream after configuring its `.env`. These checks do not start the final Resilix backend.

## Final web application


Resilix is a Bun / Next.js / TypeScript PWA for source-linked hazard awareness, private observations, conversational AI, and human-reviewed preparedness simulations. The public pitch deck is `/deck/JO202610101600`.

## Run locally

```sh
cp .env.example .env
bun install --frozen-lockfile
bun run build
bun run start
```

The default `.env.example` starts the web server on port 3000 and expects the backend on port 8080. `bun run dev` uses the same custom server. `/api/health` is the web liveness endpoint. `/api/config` exposes only map configuration. The custom server proxies bidirectional `/api/events` WebSockets; the App Router proxies approved API routes and forwards session cookies and CSRF tokens.

All network configuration is read from `runtime-config.mjs`, so a Docker image can move between environments without rebuilding public environment variables. Set `API_BASE_URL` to the backend origin. Configure `MAP_TILE_URL`, `MAP_ATTRIBUTION`, and `MAP_ATTRIBUTION_URL` together. `CSP_CONNECT_ORIGINS` is an explicit space-separated list of HTTPS/WSS provider origins; include the actual OpenAI or Azure realtime origin and Gemini Live origin used by core. No provider key is read by this app.

`docker-compose.yml` is for local development only. Production uses Azure Container Apps through the separate infrastructure repository. Each Docker build uses only this repository as its context.

## Product paths

- `/` — landing page, authentication and one-click isolated demo session; after authentication, the workspace.
- `/app` — workspace entry with the same authentication boundary.
- `/login` — public entry to the same sign-in experience.
- `/deck/JO202610101600` — nine-slide EN / ES / DE / FR deck, keyboard controls, fullscreen and print layout.
- The authenticated sidebar contains overview, geographic map, assistant, private alerts, and human-reviewed simulation proposals.

The backend creates a fresh demo account per demo request. There is no shared hardcoded demo password. Sessions use HttpOnly cookies; CSRF tokens live in memory. Private reports are read, created and deleted through owner-scoped backend endpoints. The UI never broadcasts them itself.

## AI and media

The backend catalog drives text-model selection. Auto routing stays a server responsibility. Chat responses render bounded structured cards and validated HTTPS source links. Generated images use provider-returned PNG bytes and carry an illustration label. They are not verified maps or safe evacuation routes.

OpenAI is the default voice provider. Both speech conversation and `gpt-live-transcribe` dictation negotiate WebRTC with ephemeral credentials obtained from core through the backend. Gemini Live is an explicitly selected backup: the browser sends mono PCM16 at 16 kHz and plays PCM16 responses at 24 kHz. Microphone capture starts only after the user activates a voice control and stops on hang-up, navigation away from chat, or component teardown. A provider or permission failure is visible; the UI does not silently substitute a different provider.

The Gemini browser bridge uses `ScriptProcessorNode` for the bounded prototype audio path. Real-device latency, echo behavior, interruption handling and browser-specific sample-rate support require device testing; a successful build or ephemeral token request does not prove a complete voice conversation.

## Sources and privacy

Public reports include source, observation time and simulation state. Adapter status, checked time and coverage are shown separately. USGS earthquake observations are worldwide; MeteoSwiss coverage is limited to the postal area configured in the backend. Empty or unavailable feeds are not an all-clear. Personal map markers are shown only when valid coordinates exist. Swisstopo tile requests use CORS and display attribution.

The service worker caches only the public offline page, icon and manifest. It never caches API requests, authenticated HTML, private reports, conversations, or audio. Only theme and interface language are stored in localStorage. Offline navigation returns a public four-language reconnection screen.

The web sends strict CSP with per-request nonces, anti-framing, no-sniff, referrer controls, COOP/COEP/CORP, and explicit microphone/geolocation permissions. AI and report content are rendered as text, never as raw HTML. The reverse proxy accepts a bounded route allowlist and checks cross-origin mutation requests.

## Independent UI packages

The main app consumes versioned source tarballs in `vendor/`:

- `@resilix/ui-components`: buttons, icons, badges and metrics.
- `@resilix/ui-chat`: composer and structured answer cards.
- `@resilix/ui-canvas`: attributed geographic map and coordinate projection.

Each source repository runs its own Next.js showcase and tests. Tarballs contain the actual reusable components; the application imports the packages and Next.js transpiles them. No production import or build step reaches into a sibling checkout. To update a package, bump its version, pack it with `bun pm pack`, copy it into this app’s `vendor/`, and run `bun add ./vendor/<archive>.tgz`.

The visual language follows the supplied gray/lime chat references: a fixed dark navigation rail, neutral surfaces, restrained rounded cards, source labels, compact controls and light/dark themes. CSS Modules are the sole component styling approach. Global design tokens and resets live in `src/styles/globals.css`; translations and deck copy have complete sibling language files.

## Verification

```sh
bun test
bun run lint
bun run build
```

Tests cover four-language/deck parity, alert input validation, unsafe source URL rejection, source-card schema, sensitive-data service-worker exclusions, and PCM encoding. UI repositories additionally test their rendered security/accessibility contracts and coordinate projection. Run these commands within each repository; the root also contains unrelated reference repositories whose dependencies are not installed as part of this application.

The public interface is a hackathon prototype for awareness and preparation. Resilix does not contact emergency responders, certify routes, make medical decisions, or issue real alerts. An approved workflow records a clearly labelled simulated acknowledgement. Provider credentials, source coverage, deployment state and physical microphone verification must be assessed separately from software build results.
