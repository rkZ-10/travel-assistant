# Travel Assistant

AI agent for Indian domestic flight tracking and trip booking, built with **MCP**, **RAG** and an agent layer on top.

> Status: scaffolding. Private until ready to show.

## Architecture

| Layer | What it does | Backed by |
|---|---|---|
| `mcp-server/` | MCP tools: `status_*` (flight status, delays, schedules) and `booking_*` (search, offer, order, cancel) | AirLabs (fallback: AeroDataBox) · Duffel test mode |
| `rag/` | Retrieval over fare rules, baggage/cancellation policies, DGCA passenger rules, travel policy docs | Vector store (TBD) |
| `agent/` | Plans trips, calls MCP tools, checks options against RAG, asks for approval before booking | TBD |
| `evals/` | Booking-flow scenarios, tool-call accuracy, retrieval quality | — |

## Setup

```bash
cp .env.example .env   # add your API keys
```

## Roadmap
- [ ] MCP server — flight status (AirLabs) behind a `FlightStatusProvider` interface
- [ ] MCP server — booking tools (Duffel test mode)
- [ ] RAG ingestion + retrieval
- [ ] Agent with human-in-the-loop booking approval
- [ ] Evals
