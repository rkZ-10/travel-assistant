# Travel Assistant

A personal AI assistant for Indian domestic flights. It searches live fares, answers fare-rule and
passenger-rights questions with citations, remembers your preferences, and is measured by an eval
suite. It's built with **MCP**, **RAG**, the **Claude Agent SDK** and deterministic **evals**.

📚 **Docs:** [docs/README.md](docs/README.md): architecture, design decisions, setup, operations.

## Components

| Folder | What it does | Backed by |
|---|---|---|
| [`mcp-server/`](mcp-server/README.md) | 8 MCP tools: flight search, day-of-travel status, policy search, preferences, quota usage | SerpApi (Google Flights) · AirLabs · SQLite |
| [`rag/`](rag/README.md) | Official IndiGo, Air India, Akasa and DGCA pages → hybrid retrieval with citations and freshness checks | SQLite FTS5 + local bge-small embeddings (RRF) |
| [`agent/`](agent/README.md) | Trip planner: preferences → search → fare rules and DGCA rights → cited recommendation, with guardrails enforced in code | Claude Agent SDK |
| [`evals/`](evals/README.md) | 19 cases scoring tool use, arguments, citations, and whether every ₹ amount came from a tool | Real agent runs + deterministic checks |

## Quick start (Windows)

```powershell
copy .env.example .env      # add SERPAPI_KEY and AIRLABS_API_KEY
cd mcp-server; python -m uv sync --extra dev; python -m uv run travel-rag ingest
cd ..\agent;   python -m uv sync --extra dev
python -m uv run travel-agent ask "Cheapest nonstop HYD to MAA next Friday, and the cancellation fee?" -v
python -m uv run travel-eval --model haiku
```

Full setup, including saving the bot-blocked airline pages and connecting Claude Desktop, is in
[docs/setup.md](docs/setup.md).

## Status

- [x] MCP server: search (SerpApi / Google Flights) and day-of-travel status (AirLabs)
- [x] RAG: airline and DGCA policy search with citations (hybrid BM25 + vectors)
- [x] Saved travel preferences (read/update via MCP, approval-gated writes)
- [x] Agent: Claude Agent SDK planner with guardrails and run traces
- [x] Evals: 19 deterministic cases including ₹ grounding. **Latest: sonnet 18/18, haiku 15/18** ([details](evals/baselines/README.md))
- [ ] Fix known gaps found by evals ([roadmap](docs/roadmap.md))
- [ ] Booking via a sandbox provider (no bookable flight API is available to individual developers in India)
