# travel-assistant — Claude Code Context

Personal AI assistant for Indian domestic flights: live fare search, fare-rule and passenger-rights
answers with citations, saved preferences, and an eval suite. It's a portfolio project showing MCP
server design, RAG, agent construction and evals. Full docs are in `docs/` (start with
`docs/README.md`). **Keep this file and `docs/` up to date when you change behaviour.**

## Status (2026-10-03)
- [x] MCP server: search (SerpApi Google Flights), status (AirLabs), 8 tools
- [x] RAG: airline + DGCA policies, hybrid retrieval, freshness and block-page checks
- [x] Preferences: get/update tools, approval-gated writes
- [x] Agent: Claude Agent SDK planner with code-enforced guardrails and traces
- [x] Evals: 19 cases, deterministic checks incl. ₹ grounding. Baseline 2026-10-03: sonnet 17/17, haiku 14/17 (evals/baselines/)
- [x] Post-baseline fixes: prompt hardening (prefs line, required DGCA call, exact arithmetic), max_price drops unpriced/over-budget + notes. Re-run pending
- [ ] Missing IX/SG/9I policy sources; 2026 DGCA refund CAR
- [ ] Booking via sandbox BookingProvider (no bookable API for individuals in India)

## Layout
```
mcp-server/   travel_mcp: server.py (tools), providers/ (serpapi, airlabs, base CachedHTTP),
              cache.py (SQLite TTL + quota), preferences.py, models.py, rag/ (extract, chunk,
              ingest, index, cli). CLIs: travel-mcp, travel-rag
rag/          sources.yaml (committed); manual/ + snapshots/ (gitignored captured pages)
agent/        travel_agent: runner.py, guard.py, prompts.py, trace.py, cli.py, evals/.
              CLIs: travel-agent, travel-eval
evals/        cases.yaml; results/ (gitignored); baselines/ (committed summaries)
docs/         architecture, mcp-server, rag, agent, evals, decisions, setup, operations, roadmap
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

## Conventions
- Secrets only in `.env` (CRLF-tolerant loading). Never commit `.env`, snapshots, manual saves, or .data.
- All HTTP goes through `providers/base.py` `CachedHTTP`. Validate inputs before spending quota.
- Tool outputs are compact Pydantic models; anticipated failures raise `ToolError`.
- Tests never hit live APIs: httpx.MockTransport, recorded fixtures (scrub keys and IP/geo data),
  a fake embedder for RAG.
- Agent guardrails live in code (guard.py PreToolUse hook), not only the prompt. Any write
  (preferences now, booking later) needs explicit user approval.
- The agent reaches the server only over MCP; never import travel_mcp from travel_agent.
- Commit messages end with the Co-Authored-By / Claude-Session lines when Claude commits.

## Commands
```powershell
cd mcp-server; python -m uv run pytest                       # 62 tests
python -m uv run travel-rag ingest | sources | query "..."
cd ..\agent;   python -m uv run pytest                       # 28 tests (+1 live, TRAVEL_AGENT_LIVE=1)
python -m uv run travel-agent ask "..." -v | chat
python -m uv run travel-eval [--model haiku] [--only id] [--repeat n] [--include-heavy] [--rescore <run-dir>]
```
