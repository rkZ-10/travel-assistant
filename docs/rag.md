# Policy RAG (`rag/` + `mcp-server/src/travel_mcp/rag/`)

This answers questions like "what does cancelling an IndiGo Saver fare cost 2 days out?" or "what
compensation am I owed for denied boarding?" from **official sources only**, with citations and
capture dates.

## Sources (`rag/sources.yaml`)

| Airline | Pages | How captured |
|---|---|---|
| IndiGo (6E) | Baggage, Fees & charges, Fare rules, Delays & cancellations | **Saved by hand** to `rag/manual/` (the site blocks non-browser clients) |
| Air India (AI) | Smart Fares, Baggage FAQ | Saved by hand (same reason) |
| Akasa (QP) | Baggage, FAQ | Fetched automatically |
| Air India Express (IX) | Fees & charges (mandatory-disclosure PDF), Baggage FAQ | Saved by hand: robots.txt disallows bots on its documents, and the FAQ is rendered by JavaScript |
| SpiceJet (SG) | Terms of carriage (change/cancellation fee table, baggage) | Saved by hand: an automated fetch gets an empty page |
| Alliance Air (9I) | Domestic tariff sheet (fare rules, effective 1 Sep 2025), FAQs (Aug 2025) | Fetched automatically (PDF). The tariff sheet has an old and a current (1 Aug 2025) fee table; its `note:` says which is current |
| DGCA | CAR M-IV (denied boarding/cancellation/delay, Rev 4 2023), CAR M-II (refunds, 2019 revision; **superseded** by the 26 Mar 2026 revision) | Fetched automatically (PDF) |

Not covered (the agent says so instead of guessing): Star Air, Fly91.

`ingest` honours each site's robots.txt (agent name `travel-assistant-rag`). If a site disallows
bots for a URL, the fetch stops before requesting the page and says to save it from a browser and
add a `file:` entry. Manual saves are a person reading a public page, which robots.txt doesn't
cover.
Entries can have both `url` and `file`: the saved file is indexed, and the URL is what gets cited.
The `note:` on a source is shown with every passage from it.

## Pipeline

```
sources.yaml → ingest (fetch or read file) → extract → check → snapshot (.md + meta) → chunk → index
```

1. **Fetch** with an honest User-Agent, after checking robots.txt. Bot-blocked sites are captured with a manual browser save
   instead of spoofing a browser (see [decisions.md](decisions.md)).
2. **Extract** HTML or PDF to light markdown (`extract.py`):
   - Fee **tables become pipe rows**.
   - **Tabs** (ARIA `tabpanel`, AEM `dc:title`) and **accordions** become heading levels, and
     `<p><b>…</b></p>` lines become sub-headings. Fee pages put Domestic/International in tabs
     rather than headings, so without this every table inherited an unrelated heading.
   - Duplicate blocks are removed only within the same section, so identical tables under
     different tabs both survive.
   - Forms are dropped as booking/search widgets, except a form holding most of the page:
     ASP.NET sites such as SpiceJet wrap the whole page in one `<form>`, which used to extract
     to nothing.
   - `EXTRACTOR_VERSION` makes `ingest` re-extract existing snapshots when the extractor changes,
     without re-fetching and keeping the original capture date.
3. **Check** (`check_content`) rejects JS shells, bot walls, CDN challenges and consent screens. It
   looks for block phrases near the top of the page or on short pages, plus a "no structure and
   very little text" rule. For a manual save, the error names the URL to save again.
4. **Snapshot**: `rag/snapshots/<id>.{html|pdf,md,meta.json}`. For manual saves, `fetched_at` is the
   file's save time.
5. **Chunk** (`chunk.py`): heading-aware, about 1,000 characters. Each chunk keeps its heading
   path. Long tables are split by rows with the header repeated.
6. **Index** (`index.py`, `.data/policies.sqlite3`):
   - SQLite **FTS5/BM25** for exact terms ("Flexi Plus", "4,299").
   - **`BAAI/bge-small-en-v1.5`** embeddings via fastembed (local ONNX, no API key; the model is
     cached in `.data/models`) for paraphrases. Each chunk is embedded with a contextual header
     (airline, page, section).
   - The two rankings are fused with **Reciprocal Rank Fusion** (k=60). Brute-force cosine is fine
     at about 350 chunks.
   - An airline filter always keeps DGCA rules unless `include_regulations=false`.
   - If the index was built with a different embedding model, search refuses and asks for a re-ingest.

## Freshness

- Snapshots older than **60 days** are marked `STALE` in `travel-rag sources`. Passages from them
  carry a `stale_warning` saying exactly how to update them.
- URL sources are re-fetched by `ingest` after 30 days. Manual files are re-read whenever you save
  a newer copy.

## Commands

```powershell
cd mcp-server
python -m uv run travel-rag ingest            # fetch new/stale, re-extract on version change, rebuild index
python -m uv run travel-rag ingest --refresh  # force re-fetch
python -m uv run travel-rag sources           # dates, ages, STALE flags
python -m uv run travel-rag query "IndiGo Saver cancellation fee 2 days before" --airline 6E
```

## Why snapshots aren't committed

They're copies of third-party pages. `sources.yaml` is committed, and anyone can rebuild the
snapshots with `ingest` plus the manual saves.
