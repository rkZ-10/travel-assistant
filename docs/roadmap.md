# Roadmap

## Known gaps (from manual runs and evals)
- **Conflicting sources:** the agent followed the superseded 2019 DGCA look-in rule (5 days) over
  IndiGo's current page (7 days). Fix: prompt rule to prefer current, non-superseded sources and
  flag conflicts. Tracked by `policy-conflicting-sources-look-in`.
- **No Air India Express, SpiceJet or Alliance Air policy sources.** Add official pages to `sources.yaml`.
- **2026 DGCA refund CAR** isn't indexed yet (manual download needed).
- **Fare type is assumed:** Google Flights doesn't say Saver vs Flexi. The agent states this assumption.

## Next
1. Baseline eval run → commit `evals/baselines/` → fix the known gaps → re-run and show the delta.
2. Booking via a sandbox `BookingProvider`: hold → confirm (with approval) → fake PNR → cancel.
   This reuses the approval guard.
3. Optional LLM-judge eval for answer quality (clarity, recommendation reasoning).
4. Delay alerts for a booked flight: poll AirLabs only in the hours before departure.
5. After 2026-10-30: renew AirLabs or switch status providers (one config change).
