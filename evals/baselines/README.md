# Baselines

| Date | Model | Cases passing | Est. cost/run | Notes |
|---|---|---|---|---|
| 2026-10-03 | sonnet | **17/17** | ~$0.57 | First scored run. It showed 15/17 until a checker bug was fixed (below) |
| 2026-10-03 | haiku | 14/17 | ~$0.34 | Practice model. Real misses listed below |

## 2026-10-03 findings

**1. Checker bug (not the agent).** `grounded_amounts` read JSON arrays like `[3050,6000]` as one
number, 30506000. So Google's quoted "typical range ₹3,050–6,000" looked made up in both sonnet
failures. It's fixed (each comma-separated part is also counted) and covered by a test. Both runs
were re-scored from their saved traces with `travel-eval --rescore` at no extra usage.

**2. Haiku misses (genuine):**
- `trip-cheapest-nonstop-cancel`: skipped the second, DGCA refund-rules lookup.
- `trip-round-trip`: "saves ₹190" doesn't match the difference between any two quoted fares, so it
  was an arithmetic slip that the grounding check caught.
- `prefs-default-origin-nonstop`: applied the saved preferences correctly but didn't say so.

**3. The conflicting-sources case passes.** Sonnet followed IndiGo's current 7-day rule, quoted the
superseded 2019 DGCA 5-day rule as context and flagged the conflict. Its `known-gap` tag was removed.

**4. Behaviour worth noting:** with `max_price` set and nothing under budget, SerpApi returned
unpriced itineraries. Sonnet noticed, searched again without the cap, and told the user nothing was
under ₹6,000. This should probably be handled in the server: see the roadmap.
