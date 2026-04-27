"""Query tokenization for lexical scoring (no external NLP deps)."""

from __future__ import annotations

import re
from typing import List


def _zh_ngrams(text: str) -> List[str]:
    """Generate Chinese n-grams for robust lexical recall."""
    out: List[str] = []
    n = len(text)
    # Keep the full phrase token (existing behavior), then add 2/3-grams.
    if n >= 2:
        out.append(text)
    for size in (2, 3):
        if n < size:
            continue
        for i in range(0, n - size + 1):
            out.append(text[i : i + size])
    return out


def tokenize_query(query: str) -> List[str]:
    q = (query or "").strip().lower()
    if not q:
        return []
    parts = re.findall(r"[\u4e00-\u9fff]{2,}|[a-z0-9]+", q, flags=re.I)
    seen: set[str] = set()
    out: List[str] = []
    for p in parts:
        if re.fullmatch(r"[\u4e00-\u9fff]{2,}", p):
            candidates = _zh_ngrams(p)
        else:
            candidates = [p]
        for token in candidates:
            if token not in seen:
                seen.add(token)
                out.append(token)
    return out
