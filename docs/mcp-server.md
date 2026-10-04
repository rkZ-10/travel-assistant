# MCP server (`mcp-server/`, package `travel_mcp`)

Python, MCP SDK **v2** (`from mcp.server.mcpserver import MCPServer`; v2 renamed `FastMCP`), stdio transport.

## Tools

| Tool | Backed by | Notes |
|---|---|---|
| `search_flights` | SerpApi Google Flights | One-way or round trip; class, nonstop, max price, airlines, sort; INR, `gl=in`. Returns ≤ `limit` compact itineraries, price insights, a Google Flights link, and `notes`. With `max_price`, unpriced or over-budget itineraries are dropped, because Google returns those instead of an empty list, and a note says when nothing fits |
| `get_flight_status` | AirLabs `/schedules` | Next ~12 h only. Codeshare numbers resolve to the operating flight |
| `get_route_departures` | AirLabs `/schedules` | Route departures in the next ~12 h, one row per operating flight |
| `get_api_usage` | local | Calls used this month against each provider's budget |
| `search_policies` | local index | RAG over airline and DGCA pages; see [rag.md](rag.md) |
| `list_policy_sources` | local | Sources, fetch dates, age, stale warnings |
| `get_travel_preferences` | local | Saved defaults |
| `update_travel_preferences` | local | Partial update, `clear` to reset, validated, change log kept |
| `get_booking_options` | SerpApi (booking token) | Sellers (airline direct first), fare types with prices, and the redirect URL plus form data for one itinerary. Costs 1 search, so it's meant for user clicks. Links last about 10 min |

All read tools are annotated `read_only_hint`. `update_travel_preferences` is the only write.
Search results carry `fetched_at` (kept on cache hits) and `links_valid_minutes` (30), which the UI
uses for expiry messaging. `scripts/probe_booking.py` shows what Google offers on a route (2 searches).

## Code map

```
src/travel_mcp/
  server.py        tool definitions, input validation, Services wiring (build_server/build_services)
  config.py        Settings from repo-root .env (+ env overrides, below)
  models.py        Pydantic output models (compact: they land in an LLM context window)
  cache.py         SQLite TTL cache + per-provider monthly usage counter (Store)
  preferences.py   Preferences model, PreferenceStore (JSON + history)
  providers/
    base.py        FlightSearchProvider / FlightStatusProvider protocols, CachedHTTP
    serpapi.py     GoogleFlightsProvider + parse_search
    airlabs.py     AirLabsStatusProvider + collapse_codeshares
  rag/             see rag.md
```

## Quotas and caching

| Provider | Free plan | Local budget stop | Cache TTL |
|---|---|---|---|
| SerpApi | ~250 searches/month | 90 % (225) | 30 min (24 h during evals) |
| AirLabs | 1,000 queries/month (key expires 2026-10-30) | 90 % (900) | 5 min |

- Only real network calls count against the budget. Cache hits are free, and so are network errors that never reached the API.
- The API key is stripped from cache keys.
- `get_api_usage` shows the counters, which live in `.data/travel_mcp.sqlite3`.

## Validation (before any quota is spent)

- 3-letter IATA codes. Origin and destination must differ.
- `YYYY-MM-DD` dates, in IST: not in the past, at most ~330 days ahead. Return date ≥ outbound date.
- 2-character airline codes.

Failures come back as readable `ToolError`s for the model to correct.

## AirLabs codeshares

About two thirds of rows on Indian routes are foreign codeshares (JL/QF/VS numbers on an IndiGo
plane). `collapse_codeshares` merges them into the operating flight's `marketed_as` list.

## Environment overrides

| Variable | Default | Used for |
|---|---|---|
| `TRAVEL_MCP_DATA_DIR` | `<repo>/.data` | Where the cache, index, models and preferences live |
| `TRAVEL_MCP_PREFS_DIR` | data dir | Evals give each case its own preferences |
| `TRAVEL_MCP_SEARCH_TTL` | 1800 | Evals pin search results for 24 h |
| `SERPAPI_MONTHLY_BUDGET` / `AIRLABS_MONTHLY_BUDGET` | 250 / 1000 | Change if you upgrade a plan |

## Tests

`uv run pytest` runs 65 offline tests using `httpx.MockTransport`. The fixtures include real
recorded SerpApi and AirLabs responses (keys and IP data scrubbed). `scripts/smoke_live.py
[--record]` makes 2 real calls.
