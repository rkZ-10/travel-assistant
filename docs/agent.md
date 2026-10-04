# Agent (`agent/`, package `travel_agent`)

A trip planner built on the **Claude Agent SDK** (`claude-agent-sdk`, which bundles the Claude Code
CLI). It reaches `travel-mcp` over MCP stdio and has no other tools.

## Workflow (`prompts.py`)

1. `get_travel_preferences`, applied as defaults. Anything the user says overrides them. Every
   answer opens with a "Preferences applied: …" line.
2. If the origin, destination or date is missing: ask one question rather than guess. Relative
   dates are resolved against today's date (IST), which is injected into the prompt.
3. One `search_flights` with the filters the preferences imply. Avoided airlines are dropped by the
   agent itself, since the search can't exclude them.
4. A 2–3 option shortlist: the cheapest, the best timing, and the most flexible.
5. `search_policies` for the shortlisted airlines. For cancellation, refund or change questions a
   **separate `airlines=["DGCA"]` call is required**. Google Flights doesn't say which fare type a price
   is, so the agent doesn't name one: it says the price is the basic fare and that the airline's page
   shows the exact fare type and whether a checked bag is included (a real run showed IndiGo's
   lowest as "Lite", no checked bag, below Google's price). It quotes fees only from passages, cites the source and date, and passes on stale
   warnings.
6. A recommendation, a small table, and a "Fare rules" section with citations. Prices are copied
   exactly. Any difference quoted comes with both of the prices it's based on.
   Search `notes` (e.g. "nothing under max_price") are followed and passed on to the user.

## Guardrails (`guard.py`, enforced in code)

| Layer | Mechanism |
|---|---|
| No shell, files or web | `tools=[]` |
| No foreign MCP servers or CLAUDE.md files | `strict_mcp_config=True`, `setting_sources=[]` |
| Only travel tools | PreToolUse hook denies anything else (defence in depth) |
| SerpApi quota | ≤ 4 `search_flights` per request, identical repeats blocked |
| Human in the loop | `update_travel_preferences` needs approval: y/N in `chat`, denied in `ask` unless `--allow-pref-changes` |
| Cost | `max_budget_usd` (0.50) and `max_turns` (25) per request |

The guard runs before the permission check, so it can deny even auto-allowed tools.

## Web mode (`ui_tools.py`)

`TravelAgent(..., ui=True)` (which `travel-agent web` uses) adds an in-process MCP server `ui` with
`show_flight_cards`, plus a prompt section on using it. The agent passes only flight numbers (or
`booking_token`s), a label and a note. The backend fills each card from the recorded search result
and rejects flights that weren't in this conversation's results. Flight numbers replaced tokens as
the main key after a real run where the model garbled a long token while copying it. The guard's `AGENT_DENIED` list stops the agent calling `get_booking_options`: booking links
are fetched only on a user click.

## Traces (`trace.py`)

Every request writes `.data/agent_runs/<timestamp>.json` with:

- the prompt and model
- each tool call: input, full output, a short preview, error flag, and duration (timed by
  Pre/PostToolUse hooks, since the SDK delivers messages in batches)
- any blocked calls
- the answer, turns, estimated cost, usage and session id

The evals score these files.

## Auth and cost

- **Default: your Claude Code login.** Runs count toward your Claude plan's usage. The printed
  `cost` is an API-price estimate, not a charge. For personal use on your own machine only.
- If another Claude process renews the shared login at the same moment, the run fails with an
  "OAuth token" message. `ask` retries this twice, 20 seconds apart.
- **Optional: `ANTHROPIC_API_KEY` in `.env`.** Pay-as-you-go, with its own credentials.
- A typical trip request takes 4–6 turns and about $0.05–0.08 at API prices.

## Usage

```powershell
cd agent
python -m uv run travel-agent ask "Cheapest nonstop HYD to MAA next Friday, and the cancellation fee?" -v
python -m uv run travel-agent chat
python -m uv run travel-agent web --open      # browser UI, see ui.md
```

With `-v`, `ask` and `chat` print live activity ("· Searching flights HYD → MAA…").

Options: `--model sonnet|opus|haiku|<id>` (or `TRAVEL_AGENT_MODEL`), `--budget`, `-v`.
MCP launch: the server's own `.venv` Python, falling back to `uv run`. Override with
`TRAVEL_MCP_COMMAND` (a JSON list).

## Tests

`uv run pytest` runs 48 offline tests (guard, trace, timing, hooks/activity, UI tools, config/options, CLI, web backend and bridge, evals).
`tests/test_live.py` does one real end-to-end run when `TRAVEL_AGENT_LIVE=1`.
