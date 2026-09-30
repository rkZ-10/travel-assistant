# travel-assistant — Claude Code Context

## Project Overview
AI travel assistant: Indian domestic flight tracking + booking.
Portfolio project demonstrating MCP server design, RAG and agent orchestration.

## Stack
- Python 3.12
- MCP server (Python MCP SDK)
- Search + booking: Duffel API (the agent's core flow)
- Flight info enrichment: AirLabs (schedules, on-time status) — on-demand only, no background polling; free plan 1,000 queries/month
- Duffel runs in **test mode only** (fake "Duffel Airways" bookings, no real money)
- RAG: fare rules, baggage/cancellation policies (IndiGo, Air India), DGCA passenger rules

## Structure
mcp-server/   MCP tools: status_* and booking_*
rag/          ingestion, chunking, vector store
agent/        orchestration, approval step before booking
evals/        booking-flow scenarios, RAG accuracy

## Conventions
- API keys live in .env (never committed) — see .env.example
- Cache AirLabs responses (status ~5 min, schedules a few hours) to stay within quota
- .env may have Windows CRLF line endings — strip \r when loading
- Record API responses as test fixtures; tests must not hit live APIs
- Never call booking create/cancel without an explicit user approval step
