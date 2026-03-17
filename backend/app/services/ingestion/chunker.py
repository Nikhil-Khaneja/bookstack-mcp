"""Recursive character splitter with configurable overlap.

Deterministic, no model needed. Prefers semantic boundaries:
paragraph > line > sentence > word > char.

We measure size in *characters* (not tokens) to keep the implementation
dependency-free. For the student-scale corpus this is close enough; if
fidelity to token counts matters, swap in tiktoken later — the interface
stays the same.
"""

from __future__ import annotations

from dataclasses import dataclass

from ...core.config import get_settings


@dataclass(slots=True)
class ChunkDraft:
    ord: int
    text: str
    token_count: int  # approximate: ~4 chars per token
    meta: dict


_SEPARATORS = ["\n\n", "\n", ". ", " ", ""]


def _split_with(sep: str, text: str) -> list[str]:
    if sep == "":
        return list(text)
    parts = text.split(sep)
    # Re-attach the separator to all but the last piece so joining is lossless.
    return [p + sep for p in parts[:-1]] + ([parts[-1]] if parts[-1] else [])


def _merge(parts: list[str], size: int, overlap: int, seps: list[str]) -> list[str]:
    """Greedy merge of fragments into chunks <= size with `overlap` carry-over."""
    chunks: list[str] = []
    buf = ""
    for p in parts:
        if len(buf) + len(p) <= size:
            buf += p
            continue
        if buf:
            chunks.append(buf)
            # carry the last `overlap` chars forward
            buf = buf[-overlap:] if overlap > 0 else ""
        if len(p) > size:
            # single fragment too big — split it recursively by the next-finer separator
            for sub in _recursive_split(p, size, overlap, seps):
                if len(buf) + len(sub) <= size:
                    buf += sub
                else:
                    if buf:
                        chunks.append(buf)
                        buf = buf[-overlap:] if overlap > 0 else ""
                    buf += sub
        else:
            buf += p
    if buf:
        chunks.append(buf)
    return chunks


def _recursive_split(text: str, size: int, overlap: int, seps: list[str]) -> list[str]:
    if len(text) <= size:
        return [text]
    if not seps:
        # hard-split by chars as last resort — no more separators to try
        step = max(1, size - overlap)
        return [text[i: i + size] for i in range(0, len(text), step)]
    sep, rest_seps = seps[0], seps[1:]
    parts = _split_with(sep, text)
    return _merge(parts, size, overlap, rest_seps)


def chunk_text(
    text: str, *, size: int | None = None, overlap: int | None = None
) -> list[ChunkDraft]:
    settings = get_settings()
    size = size if size is not None else settings.chunk_size
    overlap = overlap if overlap is not None else settings.chunk_overlap
    if size <= 0:
        raise ValueError("chunk size must be > 0")
    if overlap < 0 or overlap >= size:
        raise ValueError("overlap must satisfy 0 <= overlap < size")

    text = text.strip()
    if not text:
        return []

    raw = _recursive_split(text, size, overlap, _SEPARATORS)
    drafts: list[ChunkDraft] = []
    for i, chunk in enumerate(raw):
        chunk = chunk.strip()
        if not chunk:
            continue
        drafts.append(
            ChunkDraft(
                ord=i,
                text=chunk,
                token_count=max(1, len(chunk) // 4),
                meta={"size": size, "overlap": overlap},
            )
        )
    return drafts
