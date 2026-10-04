# Baselines

| Date | Model | Cases passing | Est. cost/run | Notes |
|---|---|---|---|---|
| 2026-10-03 | sonnet | **17/17** | ~$0.57 | First scored run. It showed 15/17 until a checker bug was fixed (below) |
| 2026-10-03 | haiku | 14/17 | ~$0.34 | Practice model. Real misses listed below |
| 2026-10-03b | sonnet | **18/18** | ~$0.61 | After the findings fixes: prompt v2, server max_price handling, new budget case |
| 2026-10-03b | haiku | 15/18 | ~$0.29 | Showed 11/18 until 4 over-strict checks were fixed. Its misses moved to different cases: see below |
| 2026-10-04 | sonnet | **22/22** | ~$0.84 | After the web UI, basic-fare and flight-number fixes, and new IX/SpiceJet/Alliance Air sources (4 new cases) |

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

## 2026-10-03b findings (after the fixes)

**Sonnet: 18/18.** It now opens with "Preferences applied: …", always makes the DGCA call for
cancellation questions, and the new "nothing under ₹2,500" case passes: it searched again without
the cap and said the cheapest fare was over budget.

**Haiku: 11/18 on the first scoring. 4 of the 7 failures were the checker being too strict:**
- `trip-round-trip`: "₹192 more" *was* the difference between two quoted fares, but the table
  printed them without a ₹ sign. Now any grounded number in the answer can be part of a difference.
- `prefs-budget-nothing-under`: "over your ₹2,500 budget" wasn't matched (the regex expected "over budget").
- `policy-conflicting-sources-look-in`: the page text says "7 (seven) days".
- `policy-uncovered-airline`: the answer said "not Air India Express's specific policy page".

Each fix has a test. Re-scored from saved traces: **15/18.**

**Haiku's real misses moved around between runs:**
- It still didn't open with "Preferences applied" (prefs-default-origin-nonstop).
- It asked "is that correct?" instead of searching when it already had the route, date and budget (prefs-budget-cap).
- It replied "I've noted your preference" after the save was denied, which implies it was saved (prefs-save-denied-in-ask-mode).

**Conclusion:** sonnet stays the default. Haiku's misses change from run to run (14/17, then
15/18 with different failures), so a single haiku attempt is noise. Use `--repeat 3` if you need a
real haiku number. No more prompt changes were made after sonnet reached 18/18, to keep this
baseline clean.

## 2026-10-04: regression found in the web UI

A real web run called IndiGo UpFront (the priciest fare type) "the cheapest fare type" and quoted
its ₹999 cancellation fee, also on a flight card. New case `policy-basic-fare-row` reproduces it.

- First attempt after a prompt fix: **fail**. The agent searched for "basic fare", got only
  UpFront/Stretch+ tables, and correctly refused to use them, but gave no figure.
- After telling it to name the fare type in the query (IndiGo "Saver", Air India "Basic"/"Value"):
  **3/3 pass** with sonnet (`--repeat 3`). It quotes ₹4,299 "if booked as Saver" and says the
  Lite fare has no fee table in the sources.

## 2026-10-04: SpiceJet source, and a false pass

`policy-spicejet-cancel` passed on its first run, but the answer said it couldn't find a domestic
fee: "3999" only appeared while quoting an unlabelled fragment. Two extraction problems caused it.
SpiceJet's Domestic/International tabs weren't recognised, and its fee table sat inside a list item
and came out as loose lines. Both are fixed (EXTRACTOR_VERSION 4), and the case now also fails if
the answer says it couldn't find the fee.


`--tags rag` after the extractor changes: 8/9. The one failure, `policy-uncovered-airline`, was
the case going stale: it asked about Air India Express to prove the agent admits missing sources,
and now that IX is indexed the agent correctly answered ₹4,300. That case now asks about Star Air,
and a new `policy-airindiaexpress-cancel` checks the IX fee.
