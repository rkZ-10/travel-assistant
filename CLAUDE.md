# travel-assistant — Claude Code Context

Personal AI assistant for Indian domestic flights: live fare search, fare-rule and passenger-rights
answers with citations, saved preferences, and an eval suite. It's a portfolio project showing MCP
server design, RAG, agent construction and evals. Full docs are in `docs/` (start with
`docs/README.md`; `docs/repo-map.md` explains every file, `docs/development.md` the workflow).
**Keep this file and `docs/` up to date when you change behaviour.**

## Status (2026-10-04, evening)
- [x] MCP server: search (SerpApi Google Flights), status (AirLabs), booking options, 9 tools
- [x] RAG: airline + DGCA policies, hybrid retrieval, freshness and block-page checks
- [x] Preferences: get/update tools, approval-gated writes
- [x] Agent: Claude Agent SDK planner with code-enforced guardrails and traces
- [x] Evals: 23 cases, deterministic checks incl. ₹ grounding. Latest 2026-10-03b: sonnet 18/18, haiku 15/18 (evals/baselines/README.md)
- [x] Post-baseline fixes: prompt hardening (prefs line, required DGCA call, exact arithmetic), max_price drops unpriced/over-budget + notes. Re-run done (sonnet 18/18)
- [x] React chat UI (ui/) + FastAPI WebSocket backend (travel-agent web) with live tool activity
- [x] Preferences panel (direct edit via REST → MCP bridge); flight cards grounded in search results (by flight number or booking_token), booking redirect to seller (get_booking_options on click only), expiry countdowns
- [x] Web UI Claude access: detects local Claude login, else bring-your-own API key (auth.py, Auth.tsx); key-only mode
- [ ] Host travel-mcp as a remote Claude connector so others use it on their own subscription ("option 1")
- [ ] Run scripts/probe_booking.py to confirm airline-direct sellers; use booking fare types in answers
- [x] IX/SG/9I policy sources (IX + SpiceJet = manual saves: robots.txt / JS / empty fetch); ingest honours robots.txt
- [ ] 2026 DGCA refund CAR (manual PDF); Star Air / Fly91 sources
- [ ] Booking via sandbox BookingProvider (no bookable API for individuals in India)

## Layout
```
mcp-server/   travel_mcp: server.py (tools), providers/ (serpapi, airlabs, base CachedHTTP),
              cache.py (SQLite TTL + quota), preferences.py, models.py, rag/ (extract, chunk,
              ingest, index, cli). CLIs: travel-mcp, travel-rag
rag/          sources.yaml (committed); manual/ + snapshots/ (gitignored captured pages)
agent/        travel_agent: runner.py, guard.py, hooks.py (guard+timing+events), activity.py (labels),
              prompts.py, trace.py, web.py (FastAPI WS + REST), ui_tools.py (show_flight_cards, web mode),
              mcp_bridge.py (direct MCP client for UI actions), cli.py, evals/. CLIs: travel-agent, travel-eval
ui/           React 19 + Vite + TS + Tailwind v4 chat; state.ts reducer (vitest); dist/ + node_modules gitignored
evals/        cases.yaml; results/ (gitignored); baselines/ (committed summaries)
docs/         architecture, repo-map, development, mcp-server, rag, agent, ui, evals, decisions, setup, operations, roadmap
.data/        (gitignored) API cache/quota, policies.sqlite3, models/, preferences.json, agent_runs/
```

## Key facts and constraints
- Python 3.12 on Windows. `uv` is run as `python -m uv`. Repo enforces LF (`.gitattributes`).
- MCP SDK **v2**: `from mcp.server.mcpserver import MCPServer` (FastMCP was renamed); `mcp.Client` for in-memory tests.
- SerpApi free plan ~250/month; AirLabs 1,000/month, **free key expires 2026-10-30**; AirLabs schedules cover ~12 h only.
- Quota guard stops at 90 % of each budget. Cache: search 30 min (24 h in evals), status 5 min.
- Duffel/Amadeus/Skyscanner aren't usable (see docs/decisions.md). Booking deferred.
- IndiGo and Air India block non-browser clients: their pages are **saved manually** to
  rag/manual/ (sources have both `url` and `file`). Don't add browser-spoofing headers.
- RAG: FTS5 + fastembed `BAAI/bge-small-en-v1.5` (cached in .data/models) + RRF. Bump
  `EXTRACTOR_VERSION` in rag/extract.py when extraction output changes.
- DGCA CAR M-II in the index is the 2019 version, flagged superseded (revised 26 Mar 2026).
- Agent auth: Claude Code login by default (counts toward plan usage; printed cost is an estimate);
  optional `ANTHROPIC_API_KEY`. The user doesn't want pay-as-you-go spend.
- Web UI auth (auth.py): typed key > .env key > detected Claude login. Claude login only for the
  local owner; `TRAVEL_WEB_KEY_ONLY=1` for anything others can reach (Agent SDK terms: no
  claude.ai login for third parties). Typed keys: memory only, never logged/echoed/saved.

## Conventions
- Secrets only in `.env` (CRLF-tolerant loading). Never commit `.env`, snapshots, manual saves, or .data.
- All HTTP goes through `providers/base.py` `CachedHTTP`. Validate inputs before spending quota.
- Tool outputs are compact Pydantic models; anticipated failures raise `ToolError`.
- Tests never hit live APIs: httpx.MockTransport, recorded fixtures (scrub keys and IP/geo data),
  a fake embedder for RAG.
- Agent guardrails live in code (guard.py PreToolUse hook), not only the prompt. Any write
  (preferences now, booking later) needs explicit user approval.
- The agent reaches the server only over MCP; never import travel_mcp from travel_agent.
- Web backend binds 127.0.0.1 and checks Origin on WebSocket and REST; keep it local-only.
- Cards: agent passes flight numbers (or booking_tokens) only; backend fills facts from recorded search results. Agent may never call get_booking_options (AGENT_DENIED); links fetched on user click only.
- Commit messages end with the Co-Authored-By / Claude-Session lines when Claude commits.

## Commands
```powershell
cd mcp-server; python -m uv run pytest                       # 65 tests
python -m uv run travel-rag ingest | sources | query "..."
cd ..\agent;   python -m uv run pytest                       # 48 tests (+1 live, TRAVEL_AGENT_LIVE=1)
python -m uv run travel-agent ask "..." -v | chat | web [--open]
cd ..\ui; npm install; npm run build | npm run dev (proxy to :8765) | npm test
python -m uv run travel-eval [--model haiku] [--only id] [--repeat n] [--include-heavy] [--rescore <run-dir>]
```
