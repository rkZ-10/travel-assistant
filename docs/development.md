# Development guide

## Workflow

1. Read `CLAUDE.md` and the relevant `docs/` page before changing a component.
2. Make the change and add or adjust tests. **Tests never call live APIs**: use recorded fixtures
   (scrub keys and IP/geo data) and `httpx.MockTransport`.
3. Run the suite for each component you touched (below).
4. If agent behaviour could change, run the evals (`travel-eval --model haiku` to iterate,
   `travel-eval` for a scored run) and record notable runs in `evals/baselines/`.
5. Update `docs/` and `CLAUDE.md` in the same change.
6. Commit (end the message with the Co-Authored-By / Claude-Session lines when Claude commits), then push.

## Test commands

| Component | Command | Count |
|---|---|---|
| MCP server + RAG | `cd mcp-server; python -m uv run pytest` | 62 |
| Agent, web backend, evals framework | `cd agent; python -m uv run pytest` | 38 (+1 live) |
| UI | `cd ui; npm test` and `npm run build` (type-check) | 3 |
| End-to-end (live) | `$env:TRAVEL_AGENT_LIVE=1; python -m uv run pytest tests/test_live.py -s` | 1 |
| Agent behaviour | `python -m uv run travel-eval` | 18 cases |

## Conventions

- **Boundaries.** The agent talks to the server only over MCP. All HTTP goes through `CachedHTTP`.
  Inputs are validated before spending quota.
- **Guardrails in code.** Allow-list, search cap and approvals live in `guard.py`/`hooks.py`.
  Every write (preferences now, booking later) needs explicit approval.
- **Honest sources.** Use official pages only, keep an honest User-Agent, and save manually for
  bot-blocked sites. Never spoof browser headers. Cite with the capture date.
- **Versioning.** Bump `EXTRACTOR_VERSION` when extraction output changes. Re-run
  `travel-rag ingest` when the embedding model changes.
- **Evals.** When a check fails, check the checker first. Every checker fix gets a test that uses
  the real phrasing. Don't keep tuning the prompt after a clean baseline without re-running.
- **Secrets and data.** Never commit `.env`, `.data/`, snapshots, manual saves or eval results.
- **Line endings.** LF everywhere (`.gitattributes`).

## Adding things

| To add… | Do this |
|---|---|
| A policy source | Add an entry to `rag/sources.yaml` (`file:` too if the site blocks bots), `travel-rag ingest`, check with `travel-rag query` |
| An MCP tool | Define it in `server.py` with annotations and validation, add a model in `models.py`, add tests, add it to `TRAVEL_TOOLS` in `agent/config.py` and a label in `activity.py` |
| A flight provider | Implement the protocol in `providers/base.py`, wire it in `build_services`, record fixtures |
| An eval case | Add it to `evals/cases.yaml` (relative dates, a `why`), check it with `travel-eval --list`, run it with `--only <id>` |

## Working with Cowork / Claude Code

- Cowork edits the repo from a sandbox that can't delete files without your approval. If a stale
  `.git/index.lock` appears, delete it. Commits from your own terminal or Claude Code aren't affected.
- Pushing needs your GitHub credentials, so run `git push` from your terminal.
