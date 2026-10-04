# Decisions

Most recent last. Each entry gives the context, the decision, and the consequence.

### 1. Flight search: SerpApi (Google Flights), not Amadeus, Duffel or Skyscanner (2026-09-30)
- **Amadeus Self-Service** shut down in July 2026.
- **Duffel** doesn't list India as a country of incorporation. Picking another country would mean
  misrepresenting a legal fact, so we didn't.
- **Skyscanner** is partner-only. **Kiwi Tequila** is reportedly closed to new sign-ups.
- **SerpApi's Google Flights engine** is self-serve, gives live INR fares, and has the best Indian
  domestic coverage. Its free plan is about 250 searches a month.
- **Consequence:** search only. No API available to an individual in India can book (TBO and
  Tripjack need a travel-agency registration), so booking is deferred to a sandbox provider.

### 2. Flight status: AirLabs, used only on the day of travel (2026-09-30)
- AirLabs gives real-time status for 6E, AI, SG, IX and QP. The free plan is 1,000 queries/month.
- `/schedules` only covers about 12 hours ahead, so AirLabs can't be used for planning future dates.
- About two thirds of its rows are codeshares, which we collapse into the operating flight.
- We dropped the AeroDataBox fallback once the focus became search and booking.

### 3. On-demand only, with caching and quota guards (2026-09-30)
- There's no background polling: a personal assistant only queries when you ask.
- Small free quotas mean every call goes cache → budget check → call → count. Calls stop at 90 % of each budget.

### 4. Providers behind interfaces; the agent reaches the server only over MCP (2026-09-30)
- Swapping vendors (which already happened once) touches one file.
- The agent and Claude Desktop share exactly the same capabilities.

### 5. MCP SDK v2 (2026-09-30)
- The current SDK is 2.2. `FastMCP` was renamed `MCPServer`. We built on v2 rather than pinning `<2`.

### 6. Manual saves for bot-blocked sites; no browser spoofing (2026-10-01)
- IndiGo and Air India only respond to requests that look exactly like Chrome.
- Spoofing headers would get around the airlines' deliberate bot filtering, and the code will be public.
- We keep an honest User-Agent. Those 6 pages are saved by hand: a couple of minutes, a few times a year.
- Staleness warnings and block-page detection keep this safe.

### 7. Local hybrid retrieval: FTS5 + bge-small + RRF in SQLite (2026-10-01)
- There are no extra services or API keys, and it runs offline.
- BM25 handles exact fee figures and fare names. Embeddings handle paraphrases.
- At about 350 chunks, brute-force cosine search is instant, so no vector database is needed.

### 8. Structure-aware extraction (2026-10-02)
- On the real fee page, every table was labelled "Seat Select" because Domestic/International live
  in tabs and accordions, not headings.
- We now treat tabs, accordions and bold-only lines as headings, and the extractor is versioned so
  existing snapshots get re-extracted.

### 9. Preferences: a small JSON file with approval-gated writes; no company travel policy (2026-10-02)
- This is a personal tool. Preferences are human-editable and every change is logged.
- The agent may only write them with explicit user approval, the same pattern booking will use.

### 10. Agent on the Claude Agent SDK with code-enforced guardrails (2026-10-02)
- The SDK gives the agent loop, MCP client, hooks, budgets and session handling.
- Guardrails live in a PreToolUse hook (allow-list, search cap, approval), not only in the prompt.

### 11. Auth: Claude Code login by default, API key optional (2026-10-03)
- The user didn't want pay-as-you-go spend. With the subscription login, runs count toward plan
  usage instead.
- This is for personal use only and isn't to be shipped on that login.
- Transient OAuth refresh races with other Claude processes are retried.

### 12. Deterministic evals with a grounding check; no LLM judge yet (2026-10-03)
- Checks on tool calls, arguments, citations and ₹ amounts are free, repeatable and explainable.
- An LLM judge can be added later for answer quality. It would cost usage on every run.

### 13. Booking by redirecting to the seller, not a sandbox booking provider (2026-10-04)
- Google Flights' booking options (via SerpApi `booking_token`) give each seller's fare types,
  prices and a redirect that opens the seller's page with the flight preselected.
- Real booking happens on the airline's site, so there's no payment handling or sandbox to build,
  and the user always confirms there.
- It costs 1 search per lookup, so it only happens on a user click. Tokens expire, so the UI
  shows expiry countdowns (30 min for search results, 10 min for links).
- The booking options also list real fare types (Saver vs Flexi Plus), which helps the agent stop
  assuming the fare type.

### 14. Preferences: a panel for direct edits, not per-change approval cards (2026-10-04)
- Approving one agent-proposed change at a time is clunky for settings. A form shows everything
  at once, and changes made by the user need no approval.
- Conversation cards are kept for actions such as booking links.

### 15. Cards are grounded by booking token (2026-10-04)
- The agent selects and annotates. It can't state the price, times or links on a card.
- The backend fills cards from the recorded search results and rejects unknown tokens. An eval
  (`ui-flight-cards-from-search`) checks this.

### 16. Web UI: detect the local Claude login, otherwise bring your own API key (2026-10-04)
- Goal: anyone can run the UI, not only people with Claude Code signed in.
- Anthropic doesn't allow third-party products to offer claude.ai login or plan limits to other
  people (Agent SDK docs). So the Claude login is used only for the person running the server on
  their own machine (127.0.0.1). Everyone else brings an Anthropic API key and pays for their own
  usage.
- The backend detects credentials (typed key > `.env` key > Claude Code login files) and tells the
  UI, which shows a badge and only asks for a key when nothing usable is found. Detection can't
  prove a login still works, so an expired login on the first message also switches the UI to
  "sign in again or use an API key".
- A typed key lives only in that WebSocket session's memory and that session's agent process. It
  isn't written to disk, logs or traces. "Remember on this browser" (off by default) keeps it in
  the browser's localStorage.
- `TRAVEL_WEB_KEY_ONLY=1` turns the Claude login off entirely. Any deployment reachable by other
  people must use it.
- For other people using the tools through their own Claude subscription, the plan is to host the
  MCP server as a Claude connector (later).
