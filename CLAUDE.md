# travel-assistant — Claude Code Context

## Project Overview
AI travel assistant: Indian domestic flight tracking + booking.
Portfolio project demonstrating MCP server design, RAG and agent orchestration.

## Stack
- Python 3.12
- MCP server (Python MCP SDK)
- Flight status: AirLabs (primary), AeroDataBox (fallback) — behind a `FlightStatusProvider` interface
- Booking: Duffel API in **test mode only** (fake "Duffel Airways" bookings, no real money)
- RAG: fare rules, baggage/cancellation policies (IndiGo, Air India), DGCA passenger rules

## Structure
mcp-server/   MCP tools: status_* and booking_*
rag/          ingestion, chunking, vector store
agent/        orchestration, approval step before booking
evals/        booking-flow scenarios, RAG accuracy

## Conventions
- API keys live in .env (never committed) — see .env.example
- Cache flight-status responses 1–2 min to stay within free quotas
- Record API responses as test fixtures; tests must not hit live APIs
- Never call booking create/cancel without an explicit user approval step
