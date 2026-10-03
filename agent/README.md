# travel-agent

> Full documentation: [docs/agent.md](../docs/agent.md), [docs/ui.md](../docs/ui.md), [docs/evals.md](../docs/evals.md).

A trip-planning agent built on the [Claude Agent SDK](https://code.claude.com/docs/en/agent-sdk/python).
It only uses the `travel-mcp` server, which it reaches over MCP stdio the same way Claude Desktop
does, so the agent never imports server code.

```
you ──> travel-agent (Claude Agent SDK) ──MCP stdio──> travel-mcp ──> SerpApi / AirLabs / policy index / preferences
                 └─ PreToolUse guard: travel tools only · search cap · approval for preference writes
```

## What it does for a trip request

1. Reads your saved preferences and applies them (it says which ones).
2. Asks one question if the origin, destination or date is missing.
3. Runs one `search_flights` call with the filters your preferences imply.
4. Shortlists 2–3 options: the cheapest, the best timing, and the most flexible.
5. Calls `search_policies` for those airlines' change and cancellation fees and baggage rules. It
   says it assumes the lowest fare type, and cites each source and its date.
6. Recommends one option, giving reasons in terms of your preferences.

## Guardrails (enforced in code, not just the prompt)

| Guard | Why |
|---|---|
| No built-in tools (`tools=[]`), `strict_mcp_config`, `setting_sources=[]` | The agent can't run shell commands, touch files, browse, or pick up other MCP servers or CLAUDE.md files from your machine |
| PreToolUse hook denies anything that isn't a `travel` tool | Defence in depth |
| Max 4 `search_flights` per request, identical repeats blocked | SerpApi free plan is ~250/month |
| `update_travel_preferences` needs your y/N | Human in the loop; booking will reuse this pattern |
| `max_budget_usd` (default $0.50) and `max_turns` per request | Cost ceiling |

Every run is saved to `.data/agent_runs/*.json`: prompt, tool calls with inputs, result previews and
timings, blocked calls, answer, turns and cost. The evals will score these files.

## Setup (Windows)

The agent runs on the Claude Agent SDK, which ships with its own Claude Code CLI.

- **Default: your Claude Code login (no extra spend).** Runs count against your Claude plan's usage
  limits, and the reported `cost` is an estimate, not a charge. If another Claude Code window is
  renewing the login at the same moment, the run fails with an OAuth message. `ask` retries this
  automatically. Use this only for personal use on your own machine; don't ship the agent to other
  people on your login.
- **Optional: `ANTHROPIC_API_KEY=...` in the repo-root `.env`.** Pay-as-you-go API billing, with its
  own credentials, so no login clashes.

```powershell
cd "D:\My Projects\01-travel-assistant\mcp-server"; python -m uv sync --extra dev   # server venv (once)
cd ..\agent
python -m uv sync --extra dev
python -m uv run travel-agent ask "Cheapest nonstop HYD to MAA next Friday, and the cancellation fee?" -v
python -m uv run travel-agent chat
python -m uv run travel-agent web --open     # React chat UI (build ui/ first; see docs/ui.md)
python -m uv run travel-eval                 # eval suite (see docs/evals.md)
python -m uv run pytest                      # offline unit tests
$env:TRAVEL_AGENT_LIVE=1; python -m uv run pytest tests/test_live.py -s   # one real end-to-end run
```

Options: `--model sonnet|opus|haiku|<id>` (or `TRAVEL_AGENT_MODEL` in `.env`), `--budget 0.25`.
In `ask` mode preference saves are denied unless you pass `--allow-pref-changes`; `chat` always
asks you first.
