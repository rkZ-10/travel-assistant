# rag/ — policy knowledge base

Inputs for the `search_policies` MCP tool. The code is in
`mcp-server/src/travel_mcp/rag/`.

- `sources.yaml`: which official pages and PDFs to index. Edit this file to add or remove sources.
- `manual/` (gitignored): pages and PDFs you save yourself, referenced with `file:` entries. IndiGo
  and Air India don't answer non-browser clients, so their sources have both `url:` (cited) and
  `file:` (indexed). Open each URL in a browser, save it with Ctrl+S as "Webpage, HTML only" under
  the `file:` name, then run `ingest`. Re-save a page to refresh it; `ingest` picks up newer files.
- `snapshots/` (gitignored): raw pages plus extracted text, each saved with its fetch date. Answers
  cite this date because airline policies change.

```powershell
cd ..\mcp-server
uv run travel-rag ingest              # fetch new/stale sources, rebuild the index
uv run travel-rag ingest --refresh    # re-fetch everything
uv run travel-rag query "can I cancel an IndiGo Saver fare for free?" --airline 6E
uv run travel-rag sources             # what's indexed, and when it was fetched
```

Snapshots aren't committed because they're copies of third-party pages. Run `ingest` to rebuild them.
