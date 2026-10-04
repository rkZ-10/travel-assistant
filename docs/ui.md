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
- **Flight cards** for the agent's shortlist (1–3), each with a "See booking options" button.
  Clicking it lists the sellers (airline direct first), fare types such as Saver and Flexi Plus with
  prices, and **"Book on IndiGo ↗"** buttons. Those open the seller's page with the flight
  preselected, the same redirect Google Flights uses. Payment happens on the seller's site. A popular
  route can return 20+ sellers, so the first 5 show and the rest sit behind "Show N more sellers".
- **Expiry messaging** on every card: "Fares valid for about 24 more min (fetched 10:42)". Booking
  links get their own, shorter countdown (about 10 minutes). Once a card expires, its buttons are
  disabled and it offers **Search again**, and expired booking links offer **Refresh options**.
- A **Preferences panel** (header button): a form to view and edit every saved preference directly,
  covering home airport, airlines, stops, departure window, seat, checked bag, fare flexibility,
  budget, meal and notes. It shows the last-saved time and any validation errors. Changes are made
  by you, so there's no approval step.
- Per-answer footer: tool calls, turns, time and estimated cost.
- Starter prompts, a "New chat" button (which starts a fresh agent session), a connection status
  indicator with auto-reconnect, dark mode, and a mobile layout.

If you ask the *agent* in chat to remember something, it still can't save it without approval,
which the UI doesn't offer. Use the Preferences panel instead. Preferences are shared with the CLI
and Claude Desktop because they're stored in the same file.

## How a card gets its facts (and why they can't be made up)

1. The agent calls `show_flight_cards` (an in-process display tool, web mode only) with
   `booking_token`s, a label and a note. It never passes prices or times.
2. The backend looks each token up among this conversation's real `search_flights` results, which
   the PostToolUse hook records, and fills in the airline, times, price and fetch time from there.
   Unknown tokens are rejected and the agent is told why. If the agent shows the same itinerary
   twice, the reducer replaces the earlier card instead of adding a duplicate. Cards render below
   the answer text, and the prompt tells the agent to say "the cards below".
3. Booking links are **not** fetched by the agent: `get_booking_options` is on its deny list. They're
   fetched only when you click, via `POST /api/booking-options`, which costs 1 SerpApi search.

**Expiry:** a search's `fetched_at` comes from the server and survives cache hits.
`links_valid_minutes` is 30 for search results and 10 for booking options. Google doesn't publish
how long its tokens last, so these windows are conservative.

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
| server → client | `ready {model}` · `turn_start` · `tool_start {id,tool,label,input}` · `tool_end {id,ok,duration_ms,error}` · `tool_blocked {id,label,reason}` · `flight_cards {cards}` · `answer {text,turns,cost_usd,duration_ms,tools}` · `error {message}` |
| REST | `GET /api/preferences` · `PUT /api/preferences {changes}` · `POST /api/booking-options {booking_token, origin, destination, date, return_date}` · `GET /api/health` |

The REST endpoints call travel-mcp through a direct MCP client (`mcp_bridge.py`) that's started
with the app. They don't involve the model and keep the same MCP boundary. Validation errors come
back as friendly messages, e.g. "home_airport must be a 3-letter IATA code".

- One `TravelAgent` session per WebSocket. It starts lazily on the first message, keeps context
  across turns, and handles one turn at a time.
- Activity events come from the agent's combined PreToolUse/PostToolUse hook (`hooks.py`), so a
  blocked call is never reported as started. Labels come from `activity.py`, the same ones `-v`
  prints in the CLI.
- **Security:** it binds to `127.0.0.1` only, and WebSocket connections *and* REST calls from other
  origins are rejected. Otherwise any website open in your browser could drive the agent via
  `ws://127.0.0.1:8765`.
- If a sign-in clash with another Claude window happens, the backend shows a hint and starts a fresh
  session on the next message.

## Frontend code map

```
ui/src/
  state.ts        pure reducer: server events -> turns/steps/cards (vitest)
  useAgent.ts     WebSocket lifecycle, reconnect, send/reset
  api.ts          REST calls; openBooking() POSTs the redirect form in a new tab
  time.ts         expiry countdown hook, formatting helpers
  App.tsx         layout: header, conversation, composer, preferences panel
  components/     TurnView, Activity, FlightCardView (cards, options, expiry), PreferencesPanel
                  (form -> {changes, clear}, tested), Composer, Welcome
```

## Tests

- `npm test` runs the reducer and preferences-form tests (vitest, 5 tests).
- `npm run build` type-checks.
- Backend: `agent/tests/test_web.py` uses a fake agent and a fake MCP bridge. It covers streaming
  order, session reuse and reset, error hints, origin checks (WebSocket and REST), the preferences
  and booking endpoints, a bridge that fails to start, and friendly validation errors.
- `test_ui_tools.py` covers card grounding: response-shape parsing, unknown tokens rejected, and
  the guard blocking agent booking lookups.
- `test_activity.py` covers labels and hook events (allowed, blocked, failed).
