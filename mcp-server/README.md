# travel-mcp

> Full documentation: [docs/mcp-server.md](../docs/mcp-server.md) and [docs/rag.md](../docs/rag.md).

MCP server for the Travel Assistant: flight **search** with live fares for Indian routes,
**day-of-travel status**, **airline policy RAG**, and saved **travel preferences**. It uses the
Python MCP SDK v2 (`MCPServer`) over stdio.

| Tool | Source | Use it for |
|---|---|---|
| `search_flights` | Google Flights via SerpApi | Fares on a future date: one-way or round trip, filters for class, nonstop, airlines, max price |
| `get_flight_status` | AirLabs | Delay, gate and terminal for a flight in the next ~12 h. Codeshare numbers resolve to the operating flight |
| `get_route_departures` | AirLabs | What's leaving on a route in the next ~12 h, one row per operating flight |
| `get_api_usage` | local | Calls used this month vs. budget |
| `search_policies` | local index (RAG) | Baggage, fare types, change and cancellation fees, refunds, DGCA compensation. Returns cited passages with fetch dates |
| `list_policy_sources` | local | What's indexed and when each source was fetched |
| `get_travel_preferences` | local | Saved defaults: home airport, airlines, stops, departure window, seat, budget… |
| `update_travel_preferences` | local | Change them (partial update, `clear` to reset). Every change is logged |

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

## Policy RAG

Sources are listed in [`../rag/sources.yaml`](../rag/sources.yaml) (official airline pages + DGCA CARs).

- **Ingest** (`travel-rag ingest`): fetch each source → save a dated snapshot in `rag/snapshots/` →
  extract to markdown, keeping fee **tables** as rows → split into chunks by heading, each keeping its
  heading path (`Fees and Charges > Domestic… > Saver fare`).
- **Index** (`.data/policies.sqlite3`): SQLite FTS5 for exact terms ("Flexi Plus", "4,299") plus
  local `bge-small-en-v1.5` embeddings (fastembed/ONNX, no API key) for paraphrases, fused with
  Reciprocal Rank Fusion. Each chunk is embedded with a contextual header (airline, page, section).
- **Answering**: passages carry source, URL, `fetched_on` and caveats (e.g. "superseded"), and the
  server tells the model to answer only from them. Airline filters always keep DGCA rules unless
  `include_regulations=false`.

```powershell
uv run travel-rag ingest          # first run also downloads the embedding model (~70 MB) into .data/models
uv run travel-rag query "IndiGo Saver cancellation fee 2 days before" --airline 6E
```

## Preferences

Stored in `.data/preferences.json` (gitignored, human-editable), with a change log in
`.data/preferences_history.jsonl`. The model reads them at the start of a trip request and saves
lasting ones when you say things like "always nonstop" or "stop suggesting SpiceJet".

## Setup (Windows)

API keys go in the repo-root `.env` (see `../.env.example`).

With [uv](https://docs.astral.sh/uv/):

```powershell
cd path\to\travel-assistant\mcp-server
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
      "args": ["--directory", "C:\\path\\to\\travel-assistant\\mcp-server", "run", "travel-mcp"]
    }
  }
}
```

With a pip venv, use `"command": "C:\\path\\to\\travel-assistant\\mcp-server\\.venv\\Scripts\\travel-mcp.exe"` and no args.

## Tests

`tests/fixtures/` has trimmed and full real recordings from AirLabs and SerpApi (keys and IP/geo data scrubbed), plus a synthetic SerpApi fixture used by the unit tests.
Run `scripts/smoke_live.py --record` to refresh the real recordings.
