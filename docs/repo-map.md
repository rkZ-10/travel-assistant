# Repository map

Every tracked folder and file, and what it's for. Runtime-only folders (gitignored) are listed at the end.

## Root

| Path | Purpose |
|---|---|
| `README.md` | Project overview, component table, quick start, status |
| `CLAUDE.md` | Context for Claude Code: status, layout, key facts, conventions, commands. Keep it current |
| `.env.example` | Template for `.env`: `AIRLABS_API_KEY`, `SERPAPI_KEY`, optional `ANTHROPIC_API_KEY`, `TRAVEL_AGENT_MODEL`, `TRAVEL_WEB_KEY_ONLY` |
| `.gitignore` | Excludes secrets, venvs, `.data/`, RAG snapshots and manual saves, eval results, UI build output |
| `.gitattributes` | LF line endings everywhere; CRLF for `.bat/.cmd/.ps1`; PDFs and images as binary |

## `mcp-server/`: the MCP server (`travel_mcp`)

| Path | Purpose |
|---|---|
| `pyproject.toml`, `uv.lock` | Package definition (CLIs `travel-mcp`, `travel-rag`) and pinned dependencies |
| `README.md` | Component readme and Claude Desktop config |
| `src/travel_mcp/server.py` | MCP tool definitions, input validation, service wiring (`build_server`, `build_services`) |
| `src/travel_mcp/config.py` | `Settings`: keys from the repo-root `.env`, budgets, TTLs, env overrides |
| `src/travel_mcp/models.py` | Pydantic output models (itineraries, status, policy passages, quotas) |
| `src/travel_mcp/cache.py` | `Store`: SQLite TTL cache and per-provider monthly usage counter; `QuotaExceeded` |
| `src/travel_mcp/preferences.py` | Preferences model, validated partial updates, JSON store with change history |
| `src/travel_mcp/providers/base.py` | Provider protocols and `CachedHTTP` (cache → budget → call → count → cache) |
| `src/travel_mcp/providers/serpapi.py` | Google Flights search via SerpApi; `parse_search`, `max_price` filtering and notes |
| `src/travel_mcp/providers/airlabs.py` | Day-of-travel status via AirLabs; codeshare collapsing |
| `src/travel_mcp/rag/sources.py` | Loads `rag/sources.yaml`; freshness helpers (60-day staleness) |
| `src/travel_mcp/rag/extract.py` | HTML/PDF → markdown (tables, tabs, accordions); `EXTRACTOR_VERSION` |
| `src/travel_mcp/rag/ingest.py` | Fetch or read sources, block-page checks, dated snapshots, re-extraction |
| `src/travel_mcp/rag/chunk.py` | Heading-aware chunking; tables split with the header repeated |
| `src/travel_mcp/rag/index.py` | `PolicyIndex`: FTS5 + fastembed vectors + RRF; `FastEmbedder` |
| `src/travel_mcp/rag/cli.py` | `travel-rag ingest / query / sources` |
| `scripts/smoke_live.py` | 2 real API calls; `--record` saves scrubbed fixtures |
| `scripts/probe_booking.py` | Shows Google's booking sellers for a route (2 searches); `--record` |
| `tests/` | 65 offline tests (`httpx.MockTransport`, recorded and synthetic fixtures, fake embedder) |

## `rag/`: policy sources

| Path | Purpose |
|---|---|
| `sources.yaml` | Official IndiGo, Air India, Akasa and DGCA sources (`url`, `file`, or both; `note`) |
| `README.md` | How to ingest, query and refresh |
| `manual/.gitkeep` | Keeps the folder for browser-saved pages and PDFs (contents gitignored) |

## `agent/`: trip-planning agent (`travel_agent`)

| Path | Purpose |
|---|---|
| `pyproject.toml`, `uv.lock` | Package (CLIs `travel-agent`, `travel-eval`) and pinned dependencies |
| `README.md` | Component readme |
| `src/travel_agent/config.py` | `AgentConfig`, MCP launch command, tool names, `.env` key loading |
| `src/travel_agent/prompts.py` | System prompt (workflow, date injection) |
| `src/travel_agent/guard.py` | `ToolGuard`: allow-list, search cap, approval for preference writes |
| `src/travel_agent/hooks.py` | `AgentHooks`: combined guard, timing and live-activity hook callbacks |
| `src/travel_agent/activity.py` | Human-readable tool labels ("Searching flights HYD → MAA…") |
| `src/travel_agent/trace.py` | `RunTrace` and `ToolCall`: a per-run record saved as JSON; `ToolTimer` |
| `src/travel_agent/runner.py` | `build_options`, `TravelAgent` session, `ask_once` with OAuth-race retry |
| `src/travel_agent/web.py` | FastAPI backend for the UI: WebSocket chat plus REST for preferences and booking options |
| `src/travel_agent/auth.py` | Which credentials the agent runs on (typed key > `.env` key > Claude login), login detection, key-only mode |
| `src/travel_agent/ui_tools.py` | Web-mode display tool `show_flight_cards`; `SearchRegistry` that grounds cards in search results |
| `src/travel_agent/mcp_bridge.py` | Direct MCP client to travel-mcp for UI actions; friendly validation errors |
| `src/travel_agent/cli.py` | `travel-agent ask / chat / web` |
| `src/travel_agent/evals/cases.py` | Case schema and date placeholders |
| `src/travel_agent/evals/checks.py` | Deterministic checks, including `grounded_amounts` |
| `src/travel_agent/evals/runner.py` | Runs cases with isolated preferences and pinned search cache; `rescore` |
| `src/travel_agent/evals/report.py` | Markdown and JSON reports |
| `src/travel_agent/evals/cli.py` | `travel-eval` |
| `tests/` | 48 offline tests, plus `test_live.py` (opt-in, real end-to-end) |

## `ui/`: React chat UI

| Path | Purpose |
|---|---|
| `package.json`, `package-lock.json` | Scripts (`dev`, `build`, `test`) and pinned npm dependencies |
| `vite.config.ts` | React and Tailwind plugins; dev proxy `/ws` and `/api` → `:8765` |
| `tsconfig.json`, `index.html` | TypeScript config and HTML entry |
| `src/state.ts` (+ `state.test.ts`) | Pure reducer from server events to the chat state, including cards (vitest) |
| `src/api.ts` | REST calls; `openBooking()` POSTs the seller redirect in a new tab |
| `src/time.ts` | Expiry countdown hook and formatting helpers |
| `src/prefs.test.ts` | Preferences form → `{changes, clear}` mapping test |
| `src/useAgent.ts` | WebSocket lifecycle and reconnect |
| `src/App.tsx`, `src/components/*` | Layout, turns, live activity, flight cards (`FlightCardView`), preferences panel (`PreferencesPanel`), Claude access badge and API-key form (`Auth`), composer, welcome screen |
| `src/index.css` | Tailwind import, typography plugin, table styles |

## `evals/`

| Path | Purpose |
|---|---|
| `cases.yaml` | The 23 eval cases (22 run by default) |
| `README.md` | How to run |
| `baselines/` | Committed summaries per run and `README.md` with findings and history |

## `docs/`

See [README.md](README.md) for the index.

## Gitignored runtime folders

| Path | Contents |
|---|---|
| `.env` | Your API keys |
| `.data/` | `travel_mcp.sqlite3` (cache and quota), `policies.sqlite3`, `models/` (embedding model), `preferences.json` and history, `agent_runs/` traces |
| `rag/snapshots/`, `rag/manual/*` | Captured third-party pages |
| `evals/results/` | Full eval run outputs and traces |
| `*/.venv/`, `ui/node_modules/`, `ui/dist/` | Environments and build output |
