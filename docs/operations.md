# Operations

## Quotas and costs

| Item | Limit | Where to check |
|---|---|---|
| SerpApi | ~250 searches/month, local stop at 225 | `get_api_usage` tool; serpapi.com dashboard |
| AirLabs | 1,000/month, local stop at 900. **Free key expires 2026-10-30** | `get_api_usage`; AirLabs dashboard |
| Claude (agent/evals) | Your plan's usage limits (or API billing if `ANTHROPIC_API_KEY` is set) | Claude settings / console |

A trip request uses about 1 search. Each "See booking options" click uses 1 more. An eval run uses about 6 searches the first time each day,
and 0 for re-runs that day.

## Refreshing policy sources

- `travel-rag sources` shows what's `STALE` (older than 60 days).
- **Manual pages:** save them again from the browser to the same filename, then run `travel-rag ingest`.
- **URL pages:** `travel-rag ingest --refresh`.
- **New DGCA refund CAR (2026):** download the PDF to `rag/manual/dgca-car-m2-2026.pdf`, uncomment
  its entry in `sources.yaml`, and run `ingest`.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `Failed to refresh OAuth token` | Another Claude Code or Desktop process renewing the shared login | It's retried automatically. Otherwise wait a minute or close other Claude Code windows |
| `OAuth session expired and could not be refreshed` | The stored Claude Code login itself expired (not a race) | Run `claude` in a terminal, type `/login`, then retry. Or set `ANTHROPIC_API_KEY` |
| `uv sync` fails with a locked `.exe` | Claude Desktop is running `travel-mcp` | Quit Claude Desktop from the tray, sync, then reopen |
| `ingest` timeouts on IndiGo/Air India | The site blocks non-browser clients | Use the manual saves (already configured) |
| `looks like a block or consent page` | The saved page was a cookie wall or bot check | Accept cookies in the browser and save again |
| `Policy index is empty` | `ingest` hasn't been run | `travel-rag ingest` |
| `index built with … re-run ingest` | The embedding model changed | `travel-rag ingest` |
| Git "LF will be replaced by CRLF" | Line-ending conversion | Fixed by `.gitattributes` (LF everywhere; .bat/.cmd/.ps1 use CRLF) |
| Stale `.git/index.lock` after Cowork edits | The Cowork sandbox can't delete git's lock files without permission | Delete `.git/index.lock`; commits from your own terminal are unaffected |
