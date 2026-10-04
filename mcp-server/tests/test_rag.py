import os

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


def test_fetch_respects_robots_txt(tmp_path):
    seen = []

    def handler(req):
        seen.append(req.url.path)
        if req.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /content/dam/\n")
        return httpx.Response(200, content=HTML.encode(), headers={"content-type": "text/html"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    blocked = Source(id="b", airline="IX", title="x", url="https://example.com/content/dam/fees.pdf")
    with pytest.raises(PermissionError, match="robots.txt"):
        fetch_source(blocked, tmp_path, client)
    assert "/content/dam/fees.pdf" not in seen  # the page itself was never requested
    allowed = Source(id="a", airline="SG", title="x", url="https://example.com/terms")
    assert "Saver" in fetch_source(allowed, tmp_path, client).markdown


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


def test_source_needs_a_location():
    with pytest.raises(ValueError):
        Source(id="x", airline="6E", title="x")


def test_saved_copy_is_read_from_disk_and_cites_url(tmp_path):
    page = tmp_path / "page.html"
    page.write_bytes(HTML.encode())
    src = Source(id="saved", airline="6E", title="x", url="https://example.com/fees", file=str(page))
    snap = fetch_source(src, tmp_path / "snaps", _client(b"", status=500))  # client must not be used
    assert "Saver" in snap.markdown and src.location == "https://example.com/fees"


def test_fetch_all_rereads_newer_saved_copy(tmp_path):
    page = tmp_path / "page.html"
    page.write_bytes(HTML.encode())
    src = Source(id="saved", airline="6E", title="x", url="https://example.com/fees", file=str(page))
    snaps = tmp_path / "snaps"
    assert fetch_all([src], snaps)[0].status == "fetched"
    assert fetch_all([src], snaps)[0].status == "cached"
    later = page.stat().st_mtime + 60
    os.utime(page, (later, later))
    assert fetch_all([src], snaps)[0].status == "fetched"


def test_missing_saved_copy_says_where_to_save_it(tmp_path):
    src = Source(id="saved", airline="6E", title="x", url="https://example.com/fees", file="manual/nope.html")
    report = fetch_all([src], tmp_path)[0]
    assert report.status == "failed" and "https://example.com/fees" in report.detail


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


# ------------------------------------------- structure from tabs/accordions ----
AEM_STYLE = """<html><head><title>Fees</title></head><body><main>
<h1>Fees and Charges</h1>
<div class="cmp-tabs">
  <div class="cmp-tabs__tablist">
    <button role="tab" id="t-dom">Domestic</button><button role="tab" id="t-intl">International</button>
  </div>
  <div role="tabpanel" aria-labelledby="t-dom">
    <div class="accordion-item">
      <div class="accordion-item--header"><p class="accordion-item--header-title">Changes and Cancellation</p></div>
      <div class="accordion-item--body">
        <p><b>IV. Changes and cancellation</b></p>
        <h4>Rates for Saver fare.</h4>
        <table><tr><td>Saver</td><td>Cancellation Fee</td></tr><tr><td>72h+</td><td>4299</td></tr></table>
      </div>
    </div>
  </div>
  <div role="tabpanel" aria-labelledby="t-intl" aria-hidden="true">
    <div class="accordion-item">
      <div class="accordion-item--header"><p class="accordion-item--header-title">Changes and Cancellation</p></div>
      <div class="accordion-item--body">
        <h4>Rates for Saver fare.</h4>
        <table><tr><td>Saver</td><td>Cancellation Fee</td></tr><tr><td>72h+</td><td>4299</td></tr></table>
      </div>
    </div>
  </div>
  <div role="tabpanel" data-cmp-data-layer='{"x":{"dc:title":"Codeshare"}}'>
    <p><b>Booking Fee</b></p><p>A booking fee of INR 350 applies to every booking made via the call centre.</p>
  </div>
</div></main></body></html>"""


def test_tabs_and_accordions_become_heading_path():
    md, _ = html_to_markdown(AEM_STYLE)
    paths = [c.heading for c in chunk_markdown(md) if "4299" in c.text]
    assert paths == [
        "Fees and Charges > Domestic > Changes and Cancellation > Rates for Saver fare.",
        "Fees and Charges > International > Changes and Cancellation > Rates for Saver fare.",
    ], "identical tables under different tabs must both survive, each with its own tab label"
    codeshare = next(c for c in chunk_markdown(md) if "INR 350" in c.text)
    assert codeshare.heading == "Fees and Charges > Codeshare > Booking Fee"


def test_overlong_heading_kept_as_text():
    para = "A codeshare flight is one in which one carrier markets and the other operates " * 3
    html = f"<main><h1>Fees</h1><div class='accordion-item--header'>{para}</div><p>Body text here for this section.</p></main>"
    md, _ = html_to_markdown(html)
    assert all(len(line) < 200 for line in md.splitlines() if line.startswith("#"))
    assert "codeshare flight" in md


def test_extractor_upgrade_reextracts_without_refetch(tmp_path):
    import json

    src = SOURCES[0]
    fetch_source(src, tmp_path, _client(HTML.encode()))
    meta_p = tmp_path / f"{src.id}.meta.json"
    meta = json.loads(meta_p.read_text())
    meta["extractor_version"] = 1
    meta_p.write_text(json.dumps(meta))
    (tmp_path / f"{src.id}.md").write_text("stale output")
    failing = _client(b"", status=500)  # proves no network is used
    report = fetch_all([src], tmp_path, client=failing)
    assert report[0].status == "re-extracted"
    snap = load_snapshot(src, tmp_path)
    assert "4,299" in snap.markdown and snap.fetched_at == meta["fetched_at"]


# ------------------------------------------------ block pages + staleness ----
from datetime import datetime, timedelta, timezone  # noqa: E402

from travel_mcp.rag.ingest import check_content  # noqa: E402
from travel_mcp.rag.sources import staleness_warning  # noqa: E402

LONG_POLICY = "# Baggage\n\n" + ("Checked baggage allowance is 15 kg on domestic flights. " * 90)


@pytest.mark.parametrize("page", [
    "# Access Denied\n\nYou don't have permission to access this server. Reference #18.af" + " x" * 200,
    "Checking your browser before accessing goindigo.in. This process is automatic." + " ." * 200,
    "We value your privacy. We use cookies to enhance your browsing experience..." + " ." * 200,
    "Loading please wait " * 30,  # no headings/tables, short
])
def test_block_and_consent_pages_rejected(page):
    with pytest.raises(ValueError):
        check_content(page)


def test_real_page_mentioning_captcha_in_footer_passes():
    check_content(LONG_POLICY + "\n\nThis site is protected by reCAPTCHA.")


def test_manual_save_block_page_says_how_to_fix(tmp_path):
    from travel_mcp.rag.sources import Source

    (tmp_path / "manual").mkdir()
    (tmp_path / "manual" / "x.html").write_text(
        "<html><body><main><h1>Access Denied</h1><p>Request blocked by security rules. "
        + "Ref 123. " * 60 + "</p></main></body></html>"
    )
    saved = tmp_path / "manual" / "x.html"
    src = Source(id="x", airline="6E", title="x", url="https://airline.test/x", file=str(saved))
    with pytest.raises(ValueError, match=r"Re-save https://airline.test/x as rag/"):
        fetch_source(src, tmp_path / "snaps")


def test_staleness_warning_after_60_days():
    from travel_mcp.rag.sources import Source

    now = datetime(2026, 12, 15, tzinfo=timezone.utc)
    manual = Source(id="m", airline="6E", title="m", url="https://a.test/p", file="manual/m.html")
    fetched = Source(id="f", airline="QP", title="f", url="https://b.test/p")
    fresh = (now - timedelta(days=59)).isoformat()
    old = (now - timedelta(days=74)).isoformat()
    assert staleness_warning(manual, fresh, now) is None
    assert "74 days" in staleness_warning(manual, old, now)
    assert "re-save https://a.test/p as rag/manual/m.html" in staleness_warning(manual, old, now)
    assert "--refresh" in staleness_warning(fetched, old, now)
