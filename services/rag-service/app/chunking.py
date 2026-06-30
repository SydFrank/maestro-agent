"""Simple, dependency-free recursive text chunker with overlap.

Overlap preserves context across chunk boundaries so retrieval doesn't cut a
relevant passage in half.
"""

from __future__ import annotations

from app.settings import settings


def chunk_text(text: str, *, size: int | None = None, overlap: int | None = None) -> list[str]:
    size = size or settings.chunk_size
    overlap = overlap or settings.chunk_overlap
    text = text.strip()
    if not text:
        return []

    # Prefer splitting on paragraph then sentence boundaries near the window edge.
    chunks: list[str] = []
    start = 0
    n = len(text)
    while start < n:
        end = min(start + size, n)
        if end < n:
            window = text[start:end]
            for sep in ("\n\n", "\n", "。", ". ", " "):
                idx = window.rfind(sep)
                if idx > size * 0.5:  # only break if reasonably far in
                    end = start + idx + len(sep)
                    break
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= n:
            break
        start = max(end - overlap, start + 1)
    return chunks
