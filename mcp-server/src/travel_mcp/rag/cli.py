"""travel-rag: build and query the policy index from the command line."""
from __future__ import annotations

import argparse
import sys

from ..config import Settings
from .index import FastEmbedder, PolicyIndex
from .ingest import fetch_all, load_snapshot
from .sources import age_days, load_sources, staleness_warning


def _index(settings: Settings) -> PolicyIndex:
    return PolicyIndex(
        settings.data_dir / "policies.sqlite3", FastEmbedder(cache_dir=settings.data_dir / "models")
    )


def cmd_ingest(args: argparse.Namespace) -> int:
    settings = Settings.load()
    sources = load_sources()
    if args.only:
        sources = [s for s in sources if s.id in set(args.only)]
    print(f"Fetching {len(sources)} source(s)...")
    failed = 0
    for r in fetch_all(sources, refresh=args.refresh):
        mark = {"fetched": "+", "cached": "=", "re-extracted": "~", "failed": "!"}[r.status]
        failed += r.status == "failed"
        print(f"  {mark} {r.source_id:<22} {r.status:<8} {r.detail}")
    print("Building index (first run downloads the embedding model, ~70 MB)...")
    counts = _index(settings).rebuild(load_sources())
    total = sum(counts.values())
    print(f"Indexed {total} chunks from {len(counts)} source(s).")
    return 1 if failed and not counts else 0


def cmd_query(args: argparse.Namespace) -> int:
    idx = _index(Settings.load())
    if idx.count() == 0:
        print("Index is empty; run `travel-rag ingest` first.")
        return 1
    for i, h in enumerate(idx.search(args.query, args.airline, top_k=args.k), 1):
        print(f"\n[{i}] {h.title} — {h.heading or '(top)'}  (score {h.score})")
        print(f"    {h.location}  · fetched {h.fetched_at[:10]}")
        if h.note:
            print(f"    NOTE: {h.note}")
        print("    " + h.text[:600].replace("\n", "\n    "))
    return 0


def cmd_sources(_: argparse.Namespace) -> int:
    stale = 0
    for s in load_sources():
        snap = load_snapshot(s)
        if snap:
            when = f"{snap.fetched_at[:10]} ({age_days(snap.fetched_at)}d)"
            warn = staleness_warning(s, snap.fetched_at)
        else:
            when, warn = "not fetched", None
        flag = "STALE" if warn else ""
        stale += bool(warn)
        print(f"{s.id:<22} {s.airline:<5} {when:<20} {flag:<6} {s.title}")
        if warn:
            print(f"{'':<22} -> {warn}")
    if stale:
        print(f"\n{stale} source(s) older than the freshness limit.")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="travel-rag")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("ingest", help="fetch sources and rebuild the index")
    p.add_argument("--refresh", action="store_true", help="re-fetch even if snapshot is fresh")
    p.add_argument("--only", nargs="+", metavar="ID", help="only fetch these source ids")
    p.set_defaults(fn=cmd_ingest)
    q = sub.add_parser("query", help="search the index")
    q.add_argument("query")
    q.add_argument("--airline", nargs="+", help="IATA codes, e.g. 6E AI")
    q.add_argument("-k", type=int, default=5)
    q.set_defaults(fn=cmd_query)
    s = sub.add_parser("sources", help="list sources and snapshot dates")
    s.set_defaults(fn=cmd_sources)
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
