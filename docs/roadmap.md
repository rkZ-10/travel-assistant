# Roadmap

## Known gaps (from manual runs and evals)
- **Haiku reliability:** 15/18 after the fixes, but its misses vary between runs (preferences line,
  asking for confirmation it doesn't need, wording after a denied save). Sonnet is the default
  (18/18). Measure haiku with `--repeat 3` before relying on it.
- ~~`max_price` with nothing under budget~~: fixed in the server (unpriced/over-budget results are
  dropped, with notes), and covered by `prefs-budget-nothing-under`.
- ~~No Air India Express, SpiceJet or Alliance Air policy sources~~: added 2026-10-04 (IX saved by
  hand). Star Air and Fly91 are still uncovered.
- **Alliance Air's two documents disagree** on some cancellation amounts (tariff sheet vs FAQ). The
  agent cites both; the tariff sheet is the fare-rule document.
- **2026 DGCA refund CAR** isn't indexed yet (manual download needed).
- **Fare type is assumed:** Google Flights doesn't say Saver vs Flexi. The agent states this assumption.

## Next
0. ~~Preferences panel; flight cards with booking redirect and expiry~~ (done 2026-10-04). The first probe (HYD→MAA, 2026-10-04) found Air India
   Express **airline-direct with a redirect link**, but no fare name or price in that option. Next:
   record a real fixture (`probe_booking.py --record`) to check the price fields, then use
   booking-option fare types in answers.
1. ~~Baseline eval run~~ (done 2026-10-03: sonnet 17/17). ~~Fixes for the haiku misses and
   max_price~~ (done; sonnet 18/18). Next: booking via the sandbox provider.
2. ~~Booking via a sandbox provider~~: replaced by redirecting to the seller (decision 13).
3. Optional LLM-judge eval for answer quality (clarity, recommendation reasoning).
4. Delay alerts for a booked flight: poll AirLabs only in the hours before departure.
5. Host travel-mcp as a remote MCP server people add to Claude as a custom connector, so others can
   use the tools on their own Claude subscription. Needs a public host and protection for the
   SerpApi/AirLabs quotas (per-user keys or rate limits).
6. After 2026-10-30: renew AirLabs or switch status providers (one config change).
