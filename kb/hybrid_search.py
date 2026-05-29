"""Hybrid search: ChromaDB dense + BM25 sparse + RRF fusion.

All features are gated behind ENABLE_HYBRID_SEARCH. When disabled,
the module never imports heavy deps (torch, chromadb, FlagEmbedding).
"""

from __future__ import annotations

import hashlib
import logging
import os
import time

# Ensure .env is loaded so HYBRID_EMBEDDING_API etc. are visible to os.getenv
from pathlib import Path as _Path
from dotenv import load_dotenv as _load_dotenv
_env_file = _Path(__file__).resolve().parent.parent / ".env"
_load_dotenv(_env_file)
_load_dotenv()
import pickle
import threading
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from kb.internal import InternalChunk
from kb.tokenize import tokenize_query


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


# ---------------------------------------------------------------------------
# ChromaEmbeddingStore
# ---------------------------------------------------------------------------

class ChromaEmbeddingStore:
    """Persistent ChromaDB collection with BGE-m3 embeddings.

    Supports two backends:
    - Local: BGEM3FlagModel (default, requires FlagEmbedding)
    - API:  OpenAI-compatible /v1/embeddings (set HYBRID_EMBEDDING_API=true)
    """

    def __init__(self, persist_dir: str = "data/chroma_db") -> None:
        self._persist_dir = persist_dir
        self._client: object = None
        self._collection: object = None
        self._embed_model: object = None
        self._lock = threading.Lock()
        self._use_api = _env_bool("HYBRID_EMBEDDING_API", False)
        self._loaded = False

    def _ensure_client(self) -> object:
        if self._client is None:
            import chromadb
            self._client = chromadb.PersistentClient(path=self._persist_dir)
        return self._client

    def _ensure_embed_model(self) -> object:
        if self._embed_model is not None:
            return self._embed_model
        if self._use_api:
            self._embed_model = _APIEmbedder(
                model=os.getenv("HYBRID_EMBEDDING_API_MODEL", "BAAI/bge-m3"),
            )
        else:
            from FlagEmbedding import BGEM3FlagModel
            self._embed_model = BGEM3FlagModel(
                "BAAI/bge-m3",
                use_fp16=False,
            )
        return self._embed_model

    def _embed(self, texts: List[str]) -> List[List[float]]:
        model = self._ensure_embed_model()
        if self._use_api:
            return model.encode(texts)
        else:
            dense, _ = model.encode(texts, return_dense=True, return_sparse=False)
            return dense.tolist()

    def _embed_query(self, text: str) -> List[float]:
        return self._embed([text])[0]

    def _collection_name(self) -> str:
        return "ruc_baoyan_chunks"

    def get_stored_digest(self) -> str:
        try:
            client = self._ensure_client()
            coll = client.get_collection(self._collection_name())
            meta = coll.metadata or {}
            return str(meta.get("rebuild_digest", ""))
        except Exception:
            return ""

    def rebuild(self, chunks: List[InternalChunk], digest: str) -> None:
        with self._lock:
            stored = self.get_stored_digest()
            if stored == digest and stored:
                return  # already current
            print(f"  [ChromaDB] Rebuilding vector index for {len(chunks)} chunks...")
            client = self._ensure_client()
            try:
                client.delete_collection(self._collection_name())
            except Exception:
                pass
            coll = client.create_collection(
                name=self._collection_name(),
                metadata={"rebuild_digest": digest, "hnsw:space": "cosine"},
            )
            if not chunks:
                self._collection = coll
                return
            ids: List[str] = []
            docs: List[str] = []
            metadatas: List[Dict[str, object]] = []
            for c in chunks:
                ids.append(c.doc_id)
                docs.append(f"{c.title}\n{c.text}"[:8192])
                metadatas.append({
                    "doc_id": c.doc_id,
                    "source_group": c.source_group,
                    "kb_group": c.kb_group,
                    "title": c.title,
                    "source_tag": c.source_tag,
                    "base_confidence": c.base_confidence,
                })
            embeddings = self._embed(docs)
            # Batch upsert to avoid large single-call overhead.
            batch = 256
            for i in range(0, len(ids), batch):
                coll.upsert(
                    ids=ids[i:i+batch],
                    embeddings=embeddings[i:i+batch],
                    documents=docs[i:i+batch],
                    metadatas=metadatas[i:i+batch],
                )
                if (i + batch) % 1024 == 0 or (i + batch) >= len(ids):
                    print(f"  [ChromaDB] Upserted {min(i + batch, len(ids))}/{len(ids)} vectors")
            self._collection = coll
            print(f"  [ChromaDB] Index build complete ({coll.count()} docs)")

    def query(self, text: str, top_k: int) -> List[Tuple[str, float]]:
        with self._lock:
            client = self._ensure_client()
            try:
                coll = client.get_collection(self._collection_name())
            except Exception:
                return []
            q_emb = self._embed_query(text)
            results = coll.query(query_embeddings=[q_emb], n_results=top_k)
            ids = results.get("ids", [[]])[0]
            distances = results.get("distances", [[]])[0]
            out: List[Tuple[str, float]] = []
            for doc_id, dist in zip(ids, distances):
                score = 1.0 - float(dist) if dist is not None else 0.0
                out.append((str(doc_id), score))
            return out


class _APIEmbedder:
    """Fallback embedder using OpenAI-compatible /v1/embeddings."""

    def __init__(self, model: str) -> None:
        self._model = model

    def encode(self, texts: List[str]) -> List[List[float]]:
        from openai import OpenAI
        from config import get_settings
        settings = get_settings()
        if not settings.moark_api_key:
            return [[0.0] * 1024 for _ in texts]
        client = OpenAI(base_url=settings.moark_base_url, api_key=settings.moark_api_key)
        # Batch to avoid overwhelming the API (MOARK supports up to 8 per call)
        BATCH = 8
        MAX_RETRIES = 3
        total = len(texts)
        all_embeddings: List[List[float]] = []
        for i in range(0, total, BATCH):
            batch = texts[i:i+BATCH]
            # Exponential backoff: 2s → 4s → 8s
            for retry in range(MAX_RETRIES + 1):
                try:
                    resp = client.embeddings.create(model=self._model, input=batch)
                    all_embeddings.extend(d.embedding for d in resp.data)
                    break
                except Exception as e:
                    if retry == MAX_RETRIES:
                        raise
                    wait = 2 ** (retry + 1)
                    import logging
                    logging.warning(
                        "Embedding API batch %d/%d failed (retry %d/%d, waiting %ds): %s",
                        i // BATCH + 1, (total + BATCH - 1) // BATCH,
                        retry + 1, MAX_RETRIES, wait, e,
                    )
                    time.sleep(wait)
            # Progress logging every 100 chunks
            processed = min(i + BATCH, total)
            if processed % 100 == 0 or processed == total:
                print(f"  [Embedding] {processed}/{total} chunks...")
        return all_embeddings


# ---------------------------------------------------------------------------
# BM25ChineseIndex
# ---------------------------------------------------------------------------

class BM25ChineseIndex:
    """Wrapper around BM25Okapi with Chinese n-gram tokenization."""

    def __init__(self) -> None:
        self._bm25: object = None
        self._doc_ids: List[str] = []
        self._lock = threading.Lock()

    def _tokenize(self, text: str) -> List[str]:
        tokens = tokenize_query(text)
        return tokens if tokens else text.lower().split()

    def rebuild(self, chunks: List[InternalChunk]) -> None:
        from rank_bm25 import BM25Okapi
        with self._lock:
            corpus: List[List[str]] = []
            ids: List[str] = []
            for c in chunks:
                ids.append(c.doc_id)
                corpus.append(self._tokenize(f"{c.title}\n{c.text}"))
            self._bm25 = BM25Okapi(corpus)
            self._doc_ids = ids

    def query(self, text: str, top_k: int) -> List[Tuple[str, float]]:
        with self._lock:
            if self._bm25 is None:
                return []
            tokens = self._tokenize(text)
            scores = self._bm25.get_scores(tokens)
            indexed = [(self._doc_ids[i], float(scores[i])) for i in range(len(scores))]
            indexed.sort(key=lambda x: -x[1])
            return indexed[:top_k]

    def save(self, path: str) -> None:
        with self._lock:
            if self._bm25 is None:
                return
            data = {"bm25": self._bm25, "doc_ids": self._doc_ids}
            with open(path, "wb") as f:
                pickle.dump(data, f)

    def load(self, path: str) -> bool:
        p = Path(path)
        if not p.exists():
            return False
        with self._lock:
            try:
                with open(path, "rb") as f:
                    data = pickle.load(f)
                self._bm25 = data["bm25"]
                self._doc_ids = data["doc_ids"]
                return True
            except Exception:
                return False


# ---------------------------------------------------------------------------
# RRF fusion
# ---------------------------------------------------------------------------

def rrf_fusion(
    dense_results: List[Tuple[str, float]],
    sparse_results: List[Tuple[str, float]],
    k: int = 60,
) -> List[Tuple[str, float]]:
    """Reciprocal Rank Fusion: merge two ranked lists."""
    scores: Dict[str, float] = {}
    for rank, (doc_id, _score) in enumerate(dense_results, start=1):
        scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank)
    for rank, (doc_id, _score) in enumerate(sparse_results, start=1):
        scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank)
    merged = sorted(scores.items(), key=lambda x: -x[1])
    return [(doc_id, score) for doc_id, score in merged]


# ---------------------------------------------------------------------------
# HybridSearchEngine
# ---------------------------------------------------------------------------

class HybridSearchEngine:
    """Orchestrator: dense + sparse + RRF, with lexical fallback."""

    def __init__(self, persist_dir: str = "data/chroma_db") -> None:
        self._dense = ChromaEmbeddingStore(persist_dir)
        self._sparse = BM25ChineseIndex()
        self._persist_dir = persist_dir
        self._built = False
        self._digest: str = ""
        self._chunks: List[InternalChunk] = []

    def rebuild(self, chunks: List[InternalChunk], digest: str) -> None:
        stored = self._dense.get_stored_digest()
        if stored == digest and stored:
            self._built = True
            self._digest = digest
            self._chunks = list(chunks)
            bm25_path = os.path.join(self._persist_dir, "bm25_index.pkl")
            if not self._sparse.load(bm25_path):
                self._sparse.rebuild(chunks)
                self._sparse.save(bm25_path)
            return
        self._dense.rebuild(chunks, digest)
        self._sparse.rebuild(chunks)
        bm25_path = os.path.join(self._persist_dir, "bm25_index.pkl")
        self._sparse.save(bm25_path)
        self._built = True
        self._digest = digest
        self._chunks = list(chunks)

    def query(
        self,
        text: str,
        top_k: int,
        mode: str = "hybrid",
    ) -> List[Tuple[str, float]]:
        if not self._built:
            return []

        rrf_k = _env_int("HYBRID_RRF_K", 60)
        dense_mult = _env_int("HYBRID_DENSE_TOP_K_MULT", 2)
        sparse_mult = _env_int("HYBRID_SPARSE_TOP_K_MULT", 2)

        if mode == "dense":
            return self._dense.query(text, top_k)
        if mode == "sparse":
            return self._sparse.query(text, top_k)
        if mode == "hybrid":
            dense = self._dense.query(text, top_k * dense_mult)
            sparse = self._sparse.query(text, top_k * sparse_mult)
            return rrf_fusion(dense, sparse, k=rrf_k)[:top_k]
        # mode == "lexical" handled by caller (score_chunks), not here
        return []

    def chunk_by_id(self, doc_id: str) -> Optional[InternalChunk]:
        for c in self._chunks:
            if c.doc_id == doc_id:
                return c
        return None


_hybrid_engine: Optional[HybridSearchEngine] = None
_hybrid_lock = threading.Lock()


def get_hybrid_engine() -> HybridSearchEngine:
    global _hybrid_engine
    if _hybrid_engine is not None:
        return _hybrid_engine
    with _hybrid_lock:
        if _hybrid_engine is not None:
            return _hybrid_engine
        _hybrid_engine = HybridSearchEngine()
        return _hybrid_engine
