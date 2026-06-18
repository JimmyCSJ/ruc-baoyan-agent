"""Cross-encoder reranker using bge-reranker-v2-m3.

Lazy-loaded; falls back to no-op if FlagEmbedding is unavailable or
ENABLE_RERANKER is false.
"""

from __future__ import annotations

import os
import threading
from typing import Dict, List, Optional

from graph.state import RetrievedDoc


def _env_bool(name: str, default: bool) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


def _env_int(name: str, default: int) -> int:
    v = os.getenv(name)
    if v is None:
        return default
    try:
        return int(v.strip())
    except ValueError:
        return default


class Reranker:
    """Lazy-loaded bge-reranker-v2-m3 cross-encoder."""

    def __init__(self) -> None:
        self._model: object = None
        self._lock = threading.Lock()
        self._load_attempted = False

    def _load_model(self) -> None:
        if self._load_attempted:
            return
        with self._lock:
            if self._load_attempted:
                return
            self._load_attempted = True
            try:
                from FlagEmbedding import FlagReranker
                use_fp16 = os.getenv("RERANKER_USE_FP16", "false").lower() == "true"
                self._model = FlagReranker(
                    "BAAI/bge-reranker-v2-m3",
                    use_fp16=use_fp16,
                )
            except Exception:
                self._model = None

    def rerank(
        self,
        query: str,
        docs: List[RetrievedDoc],
        top_k: Optional[int] = None,
    ) -> List[RetrievedDoc]:
        if not _env_bool("ENABLE_RERANKER", False):
            return docs
        if top_k is None:
            top_k = _env_int("RERANKER_TOP_K", 8)
        if len(docs) <= top_k:
            return docs
        if not docs:
            return docs

        self._load_model()
        if self._model is None:
            return docs

        pairs = []
        for d in docs:
            title = str(d.get("title") or "")
            content = str(d.get("content") or "")
            text = f"{title}\n{content}"[:4500]
            pairs.append([query, text])

        try:
            scores = self._model.compute_score(pairs)
        except Exception:
            return docs

        if isinstance(scores, float):
            scores = [scores]

        # Normalize to [0, 1]
        if len(scores) > 1:
            mn = min(scores)
            mx = max(scores)
            rng = mx - mn if mx != mn else 1.0
            norm_scores = [(s - mn) / rng for s in scores]
        else:
            norm_scores = [float(scores[0])] if scores else [0.5]

        for i, d in enumerate(docs):
            ns = norm_scores[i] if i < len(norm_scores) else 0.5
            d["match_score"] = ns
            old_conf = float(d.get("confidence", 0.5))
            d["confidence"] = round((old_conf + ns) / 2, 4)

        docs.sort(key=lambda d: -float(d.get("match_score", 0)))
        return docs[:top_k]


_reranker: Optional[Reranker] = None
_reranker_lock = threading.Lock()


def get_reranker() -> Reranker:
    global _reranker
    if _reranker is not None:
        return _reranker
    with _reranker_lock:
        if _reranker is not None:
            return _reranker
        _reranker = Reranker()
        return _reranker
