"""Lexical match scoring over chunks."""

from __future__ import annotations

from typing import List, Tuple

from kb.internal import InternalChunk
from kb.tokenize import tokenize_query


def score_chunks(query: str, chunks: List[InternalChunk]) -> List[Tuple[int, InternalChunk]]:
    tokens = tokenize_query(query)
    if not tokens:
        return [(0, c) for c in chunks]

    scored: List[Tuple[int, InternalChunk]] = []
    for chunk in chunks:
        hay = f"{chunk.title}\n{chunk.text}".lower()
        hits = sum(1 for t in tokens if t in hay)
        if hits > 0:
            scored.append((hits, chunk))
    scored.sort(key=lambda x: (-x[0], x[1].doc_id))
    return scored
