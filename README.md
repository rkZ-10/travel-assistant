# Travel Assistant

AI agent for Indian domestic flight search, tracking and (later) booking, built with **MCP**, **RAG** and an agent layer on top.

> Status: scaffolding. Private until ready to show.

## Architecture

| Layer | What it does | Backed by |
|---|---|---|
| `mcp-server/` | MCP tools: `search_flights`, `get_flight_status`, `get_route_departures`, `get_api_usage` ([details](mcp-server/README.md)) | SerpApi (Google Flights) · AirLabs |
| `rag/` | Retrieval over fare rules, baggage/cancellation policies, DGCA passenger rules, travel policy docs | Vector store (TBD) |
| `agent/` | Plans trips, calls MCP tools, checks options against RAG, asks for approval before booking | TBD |
| `evals/` | Booking-flow scenarios, tool-call accuracy, retrieval quality | — |

## Setup

```bash
cp .env.example .env   # add your API keys
```

## Roadmap
- [x] MCP server — flight search (SerpApi / Google Flights)
- [x] MCP server — day-of-travel status (AirLabs)
- [ ] Booking — sandbox provider (no bookable API available to individual devs in India)
- [ ] RAG ingestion + retrieval
- [ ] Agent with human-in-the-loop booking approval
- [ ] Evals
