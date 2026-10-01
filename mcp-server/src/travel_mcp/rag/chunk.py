"""Heading-aware chunking. Each chunk keeps its heading path so it can be cited and so the
embedding sees context ("IndiGo > Fees > Saver fare") rather than an orphan table row."""
from __future__ import annotations

import re
from dataclasses import dataclass

_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")


@dataclass
class Chunk:
    heading: str
    text: str


def _is_table(block: str) -> bool:
    return block.lstrip().startswith("|")


def _split_table(block: str, max_chars: int) -> list[str]:
    rows = block.splitlines()
    header, body = rows[0], rows[1:]
    parts, cur = [], [header]
    for row in body:
        if sum(len(r) + 1 for r in cur) + len(row) > max_chars and len(cur) > 1:
            parts.append("\n".join(cur))
            cur = [header]
        cur.append(row)
    parts.append("\n".join(cur))
    return parts


def chunk_markdown(md: str, max_chars: int = 1000, min_chars: int = 80) -> list[Chunk]:
    blocks = [b.strip() for b in md.split("\n\n") if b.strip()]
    path: list[str] = []
    chunks: list[Chunk] = []
    buf: list[str] = []

    def heading() -> str:
        return " > ".join(path)

    def flush() -> None:
        text = "\n\n".join(buf).strip()
        buf.clear()
        if not text:
            return
        if len(text) < min_chars and chunks and chunks[-1].heading == heading():
            chunks[-1].text += "\n\n" + text
        else:
            chunks.append(Chunk(heading(), text))

    for block in blocks:
        m = _HEADING.match(block)
        if m:
            flush()
            level = len(m.group(1))
            path[:] = path[: level - 1] + [m.group(2).strip()]
            continue
        pieces = _split_table(block, max_chars) if _is_table(block) and len(block) > max_chars else [block]
        for piece in pieces:
            if len(piece) > max_chars and not _is_table(piece):
                # Long paragraph: split on sentence boundaries.
                sentences = re.split(r"(?<=[.;:])\s+", piece)
                for s in sentences:
                    if sum(len(b) for b in buf) + len(s) > max_chars:
                        flush()
                    buf.append(s)
                continue
            if sum(len(b) + 2 for b in buf) + len(piece) > max_chars:
                flush()
            buf.append(piece)
    flush()
    return chunks
