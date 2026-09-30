# travel-mcp

MCP server for the Travel Assistant: flight **search** with live fares for Indian routes, plus
**day-of-travel status**. It uses the Python MCP SDK v2 (`MCPServer`) over stdio.

| Tool | Source | Use it for |
|---|---|---|
| `search_flights` | Google Flights via SerpApi | Fares on a future date: one-way or round trip, filters for class, nonstop, airlines, max price |
| `get_flight_status` | AirLabs | Delay, gate and terminal for a flight in the next ~12 h. Codeshare numbers resolve to the operating flight |
| `get_route_departures` | AirLabs | What's leaving on a route in the next ~12 h, one row per operating flight |
| `get_api_usage` | local | Calls used this month vs. budget |

## Design notes

- **Provider interfaces** (`providers/base.py`). The tools depend on `FlightSearchProvider` and
  `FlightStatusProvider`, not on a vendor, so you can swap SerpApi for Travelpayouts with no tool changes.
- **Quota-aware HTTP.** Each request goes: cache → budget check → call → count → cache. Free plans are
  small (SerpApi about 250/month, AirLabs 1,000/month), so calls stop at 90 % of the budget and cache
  hits are free. Results are cached in SQLite in `../.data/` (search 30 min, status 5 min).
- **Codeshare collapsing.** About 2/3 of AirLabs rows on Indian routes are foreign codeshares
  (JL/QF/VS numbers on an IndiGo plane). These are merged into the operating flight's `marketed_as` list.
- **Validation before spending quota.** IATA codes, dates (IST, not in the past, return ≥ outbound),
  and airline codes are checked before any API call. Failures come back as readable tool errors.
- **Compact outputs** (`models.py`). Tool results go into an LLM's context, so they're trimmed and typed.

## Setup (Windows)

API keys go in the repo-root `.env` (see `../.env.example`).

With [uv](https://docs.astral.sh/uv/):

```powershell
cd "D:\My Projects\01-travel-assistant\mcp-server"
uv sync --extra dev
uv run pytest                       # offline tests, no API calls
uv run python scripts/smoke_live.py # 2 real API calls
```

Or with plain pip. Use an editable install: the server finds `.env` relative to the source tree.

```powershell
python -m venv .venv
.venv\Scripts\pip install -e ".[dev]"
.venv\Scripts\python -m pytest
```

## Connect to Claude Desktop

Add this to `claude_desktop_config.json`, then fully quit and reopen Claude:

```json
{
  "mcpServers": {
    "travel-assistant": {
      "command": "uv",
      "args": ["--directory", "D:\\My Projects\\01-travel-assistant\\mcp-server", "run", "travel-mcp"]
    }
  }
}
```

With a pip venv, use `"command": "D:\\My Projects\\01-travel-assistant\\mcp-server\\.venv\\Scripts\\travel-mcp.exe"` and no args.

## Tests

`tests/fixtures/airlabs_schedules_DEL_BOM.json` is a trimmed real AirLabs response.
The SerpApi fixture is **synthetic** (built from the documented schema). Run
`scripts/smoke_live.py --record` once to save a real response next to it.
