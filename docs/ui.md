# Chat UI (`ui/` + `agent/src/travel_agent/web.py`)

A local browser chat for the agent: React 19 + Vite + TypeScript + Tailwind v4, on a small FastAPI
WebSocket backend.

```
browser (React) ──WebSocket /ws──> travel-agent web (FastAPI, 127.0.0.1:8765) ──> TravelAgent ──MCP──> travel-mcp
```

## What it shows

- Chat with markdown answers, including fare tables, links and citations.
- **Live tool activity** while the agent works: "Reading your preferences", "Searching flights
  HYD → MAA on 2026-10-09 (nonstop)", "Checking fare rules: IndiGo, DGCA rules". Each step shows a
  spinner, then a tick with its duration. Calls the guardrail blocked show as ⊘ with the reason.
- Per-answer footer: tool calls, turns, time and estimated cost.
- Starter prompts, a "New chat" button (which starts a fresh agent session), a connection status
  indicator with auto-reconnect, dark mode, and a mobile layout.

Preference saves are **denied** in the UI for now, because there's no approval dialog yet. The agent
says the preference wasn't saved. Use `travel-agent chat` (which asks y/N) to save preferences.

## Running

```powershell
cd ui;    npm install; npm run build          # once, and after UI changes
cd ..\agent; python -m uv run travel-agent web --open   # http://127.0.0.1:8765
```

For UI development with hot reload, run `travel-agent web` in one terminal and `npm run dev` in
`ui/` in another, then open http://localhost:5173. Vite proxies `/ws` and `/api` to :8765.

## Backend protocol (`web.py`)

| Direction | Message |
|---|---|
| client → server | `{"type":"message","text":"…"}`, `{"type":"reset"}` |
| server → client | `ready {model}` · `turn_start` · `tool_start {id,tool,label,input}` · `tool_end {id,ok,duration_ms,error}` · `tool_blocked {id,label,reason}` · `answer {text,turns,cost_usd,duration_ms,tools}` · `error {message}` |

- One `TravelAgent` session per WebSocket. It starts lazily on the first message, keeps context
  across turns, and handles one turn at a time.
- Activity events come from the agent's combined PreToolUse/PostToolUse hook (`hooks.py`), so a
  blocked call is never reported as started. Labels come from `activity.py`, the same ones `-v`
  prints in the CLI.
- **Security:** it binds to `127.0.0.1` only, and WebSocket connections from other origins are
  rejected. Otherwise any website open in your browser could drive the agent via
  `ws://127.0.0.1:8765`.
- If a sign-in clash with another Claude window happens, the backend shows a hint and starts a fresh
  session on the next message.

## Frontend code map

```
ui/src/
  state.ts        pure reducer: server events -> turns/steps (unit-tested with vitest)
  useAgent.ts     WebSocket lifecycle, reconnect, send/reset
  App.tsx         layout: header, conversation, composer
  components/     TurnView (bubbles + markdown), Activity (live steps), Composer, Welcome
```

## Tests

- `npm test` runs the reducer tests (vitest).
- `npm run build` type-checks.
- Backend: `agent/tests/test_web.py` uses a fake agent and covers streaming order, session reuse
  and reset, error hints, the origin check, and health.
- `test_activity.py` covers labels and hook events (allowed, blocked, failed).
