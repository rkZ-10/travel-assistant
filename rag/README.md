# rag/ — policy knowledge base

Inputs for the `search_policies` MCP tool. The code is in
`mcp-server/src/travel_mcp/rag/`.

- `sources.yaml`: which official pages and PDFs to index. Edit this file to add or remove sources.
- `manual/` (gitignored): pages and PDFs you save yourself, referenced with `file:` entries. IndiGo
  and Air India don't answer non-browser clients, so their sources have both `url:` (cited) and
  `file:` (indexed). Open each URL in a browser, save it with Ctrl+S as "Webpage, HTML only" under
  the `file:` name, then run `ingest`. Re-save a page to refresh it; `ingest` picks up newer files.
  Air India Express is saved by hand too: download its fees PDF from the browser, and save its
  baggage FAQ as "Webpage, Complete" (the page is built by JavaScript, so "HTML only" would be an
  empty shell). `ingest` also honours robots.txt, and a URL a site disallows for bots must be
  saved this way.
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

**Freshness and sanity checks**

- Snapshots older than 60 days are marked `STALE` in `travel-rag sources`, and `search_policies`
  attaches a `stale_warning` to their passages that says how to update them.
- `ingest` rejects pages that look like a bot wall, CDN challenge or cookie-consent screen, or that
  have almost no text. For a manually saved page, the error tells you which URL to save again.
