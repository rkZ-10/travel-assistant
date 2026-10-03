# evals/

`cases.yaml` holds the eval suite for the travel agent. The runner and checks live in
`agent/src/travel_agent/evals/`. Full write-up: [docs/evals.md](../docs/evals.md).

```powershell
cd ..\agent
python -m uv run travel-eval --list                 # what's in the suite
python -m uv run travel-eval --model haiku          # cheap practice run
python -m uv run travel-eval                        # scored run (sonnet)
python -m uv run travel-eval --only policy-akasa-baggage --repeat 3
python -m uv run travel-eval --include-heavy        # also the 4-search guardrail case
```

- `results/<timestamp>-<model>/` (gitignored): `summary.md`, `results.json`, and the full agent trace
  for every case.
- `baselines/`: copy a run's `summary.md` here when it's worth keeping, so the history shows in git.
