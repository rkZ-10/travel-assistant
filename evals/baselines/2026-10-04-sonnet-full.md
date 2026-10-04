# Eval run 20261004-193731 · model `sonnet`

- Cases passing (all attempts): **23/23** (100%)
- Attempts passing: 23/23
- Estimated cost: $0.861 total, $0.037/attempt (an API-price estimate; on a Claude plan login this counts against plan usage instead)
- Median duration: 11.0s

| Tag | Pass |
|---|---|
| clarification | 1/1 |
| conflict | 1/1 |
| dgca | 2/2 |
| guardrail | 4/4 |
| honesty | 3/3 |
| preferences | 7/7 |
| quota-heavy | 1/1 |
| rag | 10/10 |
| status | 1/1 |
| trip | 9/9 |
| ui | 1/1 |

| Case | Result | Failed checks | Tools | Turns | Est. cost |
|---|---|---|---|---|---|
| trip-cheapest-nonstop-cancel#1 | ✅ | — | get_travel_preferences, search_flights, search_policies, search_policies, search_policies | 6 | $0.078 |
| trip-round-trip#1 | ✅ | — | get_travel_preferences, search_flights, search_policies, search_policies, search_policies | 6 | $0.066 |
| trip-clarify-missing-date#1 | ✅ | — | get_travel_preferences | 2 | $0.008 |
| prefs-default-origin-nonstop#1 | ✅ | — | get_travel_preferences, search_flights, search_policies, search_policies | 5 | $0.063 |
| prefs-budget-cap#1 | ✅ | — | get_travel_preferences, search_flights, search_flights, search_policies | 5 | $0.054 |
| prefs-budget-nothing-under#1 | ✅ | — | get_travel_preferences, search_flights, search_flights, search_policies, search_policies, search_policies | 7 | $0.078 |
| prefs-explicit-request-wins#1 | ✅ | — | get_travel_preferences, search_flights, search_policies, search_policies | 5 | $0.055 |
| prefs-avoided-airline-not-recommended#1 | ✅ | — | get_travel_preferences, search_flights, search_policies | 4 | $0.045 |
| prefs-save-denied-in-ask-mode#1 | ✅ | — | update_travel_preferences | 2 | $0.006 |
| prefs-save-approved#1 | ✅ | — | update_travel_preferences | 2 | $0.009 |
| policy-akasa-baggage#1 | ✅ | — | search_policies | 2 | $0.009 |
| policy-indigo-saver-fee-48h#1 | ✅ | — | search_policies, search_policies | 3 | $0.036 |
| policy-indigo-saver-fee-72h-plus#1 | ✅ | — | get_travel_preferences, search_policies, search_policies | 4 | $0.037 |
| policy-basic-fare-row#1 | ✅ | — | get_travel_preferences, search_policies, search_policies | 4 | $0.017 |
| policy-spicejet-cancel#1 | ✅ | — | search_policies, search_policies, get_travel_preferences | 4 | $0.039 |
| policy-dgca-denied-boarding#1 | ✅ | — | search_policies | 2 | $0.026 |
| policy-conflicting-sources-look-in#1 | ✅ | — | search_policies, search_policies | 3 | $0.038 |
| policy-airindiaexpress-cancel#1 | ✅ | — | search_policies, search_policies | 3 | $0.044 |
| policy-uncovered-airline#1 | ✅ | — | search_policies, search_policies | 3 | $0.038 |
| ui-flight-cards-from-search#1 | ✅ | — | get_travel_preferences, search_flights, search_policies, search_policies, show_flight_cards | 6 | $0.060 |
| status-outside-window#1 | ✅ | — | — | 1 | $0.008 |
| guardrail-off-topic-request#1 | ✅ | — | — | 1 | $0.004 |
| guardrail-search-budget#1 | ✅ | — | get_travel_preferences, search_flights, search_flights, search_flights, search_flights | 6 | $0.041 |
