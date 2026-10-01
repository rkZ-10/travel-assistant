import httpx
import pytest

from travel_mcp.rag.chunk import chunk_markdown
from travel_mcp.rag.extract import html_to_markdown
from travel_mcp.rag.index import PolicyIndex, fts_query
from travel_mcp.rag.ingest import fetch_all, fetch_source, load_snapshot
from travel_mcp.rag.sources import Source, load_sources

from .conftest import FIXTURES
from .rag_helpers import AKASA_MD, DGCA_MD, SOURCES, FakeEmbedder, write_snapshot

HTML = (FIXTURES / "policy_indigo_fees.synthetic.html").read_text(encoding="utf-8")


# ---------------------------------------------------------------- extract ----
def test_html_extraction_keeps_content_drops_chrome():
    md, title = html_to_markdown(HTML)
    assert title == "Fees and Charges | IndiGo"
    assert "### Saver fare" in md
    assert "| More than 72 hours | 3,499 | 4,299 |" in md
    assert "Call centre cancellations" in md
    for junk in ("cookies", "All rights reserved", "var x", "Book"):
        assert junk not in md


# ------------------------------------------------------------------ chunk ----
def test_chunks_carry_heading_path_and_keep_tables_whole():
    md, _ = html_to_markdown(HTML)
    chunks = chunk_markdown(md)
    saver = next(c for c in chunks if "4,299" in c.text)
    assert saver.heading == "Fees and Charges > Domestic change and cancellation fees > Saver fare"
    assert saver.text.count("|") > 10  # full table, header included
    assert any(c.heading.endswith("Look-in option") for c in chunks)


def test_long_tables_split_with_repeated_header():
    rows = "\n".join(f"| {i} hours | {i*10} |" for i in range(60))
    md = "## Fees\n\n| Time | Fee |\n" + rows
    chunks = chunk_markdown(md, max_chars=300)
    assert len(chunks) > 1
    assert all(c.text.startswith("| Time | Fee |") for c in chunks)
    assert all(len(c.text) <= 340 for c in chunks)


# ----------------------------------------------------------------- ingest ----
def _client(body: bytes, ctype="text/html", status=200):
    return httpx.Client(transport=httpx.MockTransport(
        lambda req: httpx.Response(status, content=body, headers={"content-type": ctype})
    ))


def test_fetch_writes_dated_snapshot(tmp_path):
    src = SOURCES[0]
    snap = fetch_source(src, tmp_path, _client(HTML.encode()))
    assert {p.name for p in tmp_path.iterdir()} == {
        "t-indigo-fees.html", "t-indigo-fees.md", "t-indigo-fees.meta.json"
    }
    assert load_snapshot(src, tmp_path).fetched_at == snap.fetched_at


def test_fetch_rejects_js_shell(tmp_path):
    shell = b"<html><body><div id='root'></div><script>app()</script></body></html>"
    with pytest.raises(ValueError, match="JavaScript"):
        fetch_source(SOURCES[0], tmp_path, _client(shell))


def test_fetch_all_reports_failures_and_uses_cache(tmp_path):
    ok = fetch_all(SOURCES[:1], tmp_path, client=_client(HTML.encode()))
    assert ok[0].status == "fetched"
    again = fetch_all(SOURCES[:1], tmp_path, client=_client(b"", status=500))
    assert again[0].status == "cached"
    refreshed = fetch_all(SOURCES[:1], tmp_path, refresh=True, client=_client(b"", status=500))
    assert refreshed[0].status == "failed" and "keeping older snapshot" in refreshed[0].detail


def test_sources_yaml_is_valid():
    sources = load_sources()
    assert len(sources) >= 8
    assert all(s.url or s.file for s in sources)


def test_source_needs_exactly_one_location():
    with pytest.raises(ValueError):
        Source(id="x", airline="6E", title="x")


# ------------------------------------------------------------------ index ----
@pytest.fixture
def index(tmp_path):
    md, _ = html_to_markdown(HTML)
    write_snapshot(tmp_path, SOURCES[0], md)
    write_snapshot(tmp_path, SOURCES[1], AKASA_MD)
    write_snapshot(tmp_path, SOURCES[2], DGCA_MD)
    idx = PolicyIndex(":memory:", FakeEmbedder())
    counts = idx.rebuild(SOURCES, tmp_path)
    assert all(counts[s.id] > 0 for s in SOURCES)
    return idx


def test_fts_query_sanitises():
    assert fts_query('What is the "Saver" fee?') == '"saver" OR "fee"'
    assert fts_query("?? !!") == ""


def test_search_finds_fee_table(index):
    hits = index.search("Saver fare cancellation fee more than 72 hours", top_k=3)
    assert "4,299" in hits[0].text
    assert hits[0].heading.endswith("Saver fare")
    assert hits[0].fetched_at.startswith("2026-10-02")


def test_exact_number_matches_via_keywords(index):
    hits = index.search("700 per kg", top_k=2)
    assert hits[0].airline == "QP"


def test_airline_filter_keeps_regulator(index):
    hits = index.search("compensation denied boarding baggage fee", airlines=["6E"], top_k=10)
    assert {h.airline for h in hits} <= {"6E", "DGCA"}
    assert any(h.airline == "DGCA" and h.note for h in hits)
    only = index.search("denied boarding", airlines=["6E"], include_regulations=False, top_k=10)
    assert {h.airline for h in only} == {"6E"}


def test_model_mismatch_detected(index):
    index.embedder.model_name = "other-model"
    assert "re-run ingest" in index.model_mismatch()
