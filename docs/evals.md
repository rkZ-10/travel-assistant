# Evals

**Why:** a fluent answer can still be wrong in ways only a careful read catches. The first manual
run, for example, guessed a refund figure without checking the DGCA rules. Evals turn behaviours
like that into checks that run every time.

## How it works

- **Cases** are in `evals/cases.yaml` (19 cases; 18 run by default). Each has a prompt, tags, a
  `why`, optional preferences, and checks.
- **Isolation:** each case gets a temporary preferences directory (`TRAVEL_MCP_PREFS_DIR`), so your
  real preferences are never read or changed.
- **Pinned results:** flight searches are cached for 24 h during evals (`TRAVEL_MCP_SEARCH_TTL`).
  Re-runs within a day cost no SerpApi quota and compare like with like.
- **Relative dates:** `{date+14}` in prompts and `{iso+14}` in expected arguments, so cases never go stale.
- **Real agent:** every case goes through the same `ask_once` path as the CLI, guardrails and all.

## Checks (deterministic, no LLM judge)

| Check | Catches |
|---|---|
| `first_tool`, `tools_include/exclude`, `max_calls` | Skipped preferences, needless searches, quota waste |
| `tool_args` (`contains`, `present`, `max`) | Wrong origin or date, preferences not applied, missing DGCA lookup |
| `denied` | A guardrail that didn't fire |
| `asks_question` | Guessing instead of clarifying |
| `answer_matches / not_matches` | Wrong fee band, recommending an avoided airline, claiming a save that didn't happen |
| `cites_policy_date` | Uncited policy claims |
| **`grounded_amounts`** | **Hallucinated money.** Every ₹ amount in the answer must appear in a tool output. The only exception is the sum or difference of two other grounded amounts quoted in the same answer ("₹230 more") |

## Coverage

trip (4) · preferences (7) · RAG (6) · DGCA (2) · honesty (3) · guardrails (3) · status (1).
`policy-conflicting-sources-look-in` reproduces a real conflict found by hand (the 2019 DGCA rule says
5 days, IndiGo's current page says 7). It passes on sonnet.

## Results

See [evals/baselines/](../evals/baselines/README.md). As of 2026-10-03: **sonnet 17/17, haiku 14/17.**
The first sonnet run scored 15/17. Both failures turned out to be a bug in the grounding checker,
not the agent. Check the checker before blaming the agent.

## Running

```powershell
cd agent
python -m uv run travel-eval --list
python -m uv run travel-eval --model haiku        # practice run
python -m uv run travel-eval                      # scored run
python -m uv run travel-eval --only <id> --repeat 3
python -m uv run travel-eval --include-heavy      # + the 4-search guardrail case
python -m uv run travel-eval --rescore <run-dir>  # re-check saved traces after fixing a check (no agent calls)
```

Output: `evals/results/<timestamp>-<model>/summary.md` (pass rate, results by tag, a per-case
table with failed checks, tools, turns, estimated cost), `results.json`, and full traces. Copy
summaries worth keeping into `evals/baselines/`.

**Usage:** a default run is 18 agent requests, with about 6 live searches on the first run of the
day. On a Claude plan login it counts toward plan usage. The estimate is about $1 at API prices
for sonnet.

## Reading a failure

1. Open `summary.md` and find the failed check name and its detail.
2. Open `traces/<case>-<attempt>/*.json` to see the exact tool inputs and outputs and the answer.
3. Decide whether it's an agent bug (fix the prompt or guard), a data gap (add or refresh a source),
   or a check that's too strict (fix the case), and note which.
