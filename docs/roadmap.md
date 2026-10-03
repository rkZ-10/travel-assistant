# Roadmap

## Known gaps (from manual runs and evals)
- **Haiku reliability:** 15/18 after the fixes, but its misses vary between runs (preferences line,
  asking for confirmation it doesn't need, wording after a denied save). Sonnet is the default
  (18/18). Measure haiku with `--repeat 3` before relying on it.
- ~~`max_price` with nothing under budget~~: fixed in the server (unpriced/over-budget results are
  dropped, with notes), and covered by `prefs-budget-nothing-under`.
- **No Air India Express, SpiceJet or Alliance Air policy sources.** Add official pages to `sources.yaml`.
- **2026 DGCA refund CAR** isn't indexed yet (manual download needed).
- **Fare type is assumed:** Google Flights doesn't say Saver vs Flexi. The agent states this assumption.

## Next
0. UI approval dialog so preference saves work in the browser (and the same pattern is ready for booking).
1. ~~Baseline eval run~~ (done 2026-10-03: sonnet 17/17). ~~Fixes for the haiku misses and
   max_price~~ (done; sonnet 18/18). Next: booking via the sandbox provider.
2. Booking via a sandbox `BookingProvider`: hold → confirm (with approval) → fake PNR → cancel.
   This reuses the approval guard.
3. Optional LLM-judge eval for answer quality (clarity, recommendation reasoning).
4. Delay alerts for a booked flight: poll AirLabs only in the hours before departure.
5. After 2026-10-30: renew AirLabs or switch status providers (one config change).
