# Roadmap

## Known gaps (from manual runs and evals)
- **Haiku reliability:** 14/17. It skips the DGCA refund lookup, makes small arithmetic slips, and
  doesn't always say which preferences it applied. Sonnet passes all of these. Consider tightening
  the prompt if haiku should become the default.
- **`max_price` with nothing under budget:** SerpApi returns unpriced itineraries. The server should
  drop unpriced results when `max_price` is set and report "nothing under budget; cheapest was X".
- **No Air India Express, SpiceJet or Alliance Air policy sources.** Add official pages to `sources.yaml`.
- **2026 DGCA refund CAR** isn't indexed yet (manual download needed).
- **Fare type is assumed:** Google Flights doesn't say Saver vs Flexi. The agent states this assumption.

## Next
1. ~~Baseline eval run~~ (done 2026-10-03: sonnet 17/17). Next: fix the haiku misses and the
   max_price handling, then re-run and record the delta.
2. Booking via a sandbox `BookingProvider`: hold → confirm (with approval) → fake PNR → cancel.
   This reuses the approval guard.
3. Optional LLM-judge eval for answer quality (clarity, recommendation reasoning).
4. Delay alerts for a booked flight: poll AirLabs only in the hours before departure.
5. After 2026-10-30: renew AirLabs or switch status providers (one config change).
