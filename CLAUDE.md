# travel-assistant — Claude Code Context

## Project Overview
AI travel assistant: Indian domestic flight tracking + booking.
Portfolio project demonstrating MCP server design, RAG and agent orchestration.

## Stack
- Python 3.12
- MCP server (Python MCP SDK)
- MCP SDK v2 (`from mcp.server.mcpserver import MCPServer`) — FastMCP was renamed in v2
- Search: SerpApi Google Flights engine (live fares, INR, gl=in) — free plan ~250 searches/month
- Day-of-travel status: AirLabs `schedules` (rolling ~12h window only) — free plan 1,000/month, expires 2026-10-30
- On-demand only, no background polling
- Booking: deferred. Duffel doesn't onboard India-incorporated accounts; plan is a sandbox BookingProvider
- RAG: rag/sources.yaml -> `travel-rag ingest` -> rag/snapshots (gitignored) -> .data/policies.sqlite3 (FTS5 + fastembed bge-small, RRF)
- Preferences: .data/preferences.json via get/update_travel_preferences (personal use only, no company policy)

## Structure
mcp-server/   MCP server package (src/travel_mcp): tools, providers, SQLite cache/quota
rag/          sources.yaml + manual/ PDFs (code lives in mcp-server/src/travel_mcp/rag)
agent/        travel_agent package (Claude Agent SDK); talks to travel-mcp over MCP stdio only
evals/        booking-flow scenarios, RAG accuracy

## Conventions
- API keys live in .env (never committed) — see .env.example
- All HTTP goes through providers/base.py CachedHTTP (cache -> budget check -> call -> count); search TTL 30 min, status 5 min
- AirLabs rows are mostly codeshares — collapse to operating flights (cs_flight_iata)
- Tests: `uv run pytest` in mcp-server/ — offline, httpx.MockTransport + fixtures
- .env may have Windows CRLF line endings — strip \r when loading
- Record API responses as test fixtures; tests must not hit live APIs
- Never call booking create/cancel without an explicit user approval step

## Agent (agent/)
- claude-agent-sdk (bundles the CLI). Options: tools=[], strict_mcp_config, setting_sources=[]
- Guardrails live in guard.py (PreToolUse hook), not only in the prompt: travel tools only, search cap, approval for preference writes
- Runs saved to .data/agent_runs/*.json (input for evals)
- `uv run pytest` offline; tests/test_live.py needs TRAVEL_AGENT_LIVE=1 (+ ANTHROPIC_API_KEY)
