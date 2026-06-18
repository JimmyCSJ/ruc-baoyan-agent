# RAG Engineering Notes

This project is a product-oriented RAG system for RUC baoyan consultation. The
frontend, auth, long-plan report, quick Q&A, retrieval preview, and KB admin
surfaces are all part of the product shell. The RAG core should evolve without
breaking that shell.

## Core Flow

```text
server.py / app.py
  -> graph/builder.py
  -> graph/nodes.py
  -> agents/router.py
  -> agents/retrieval.py
  -> kb/service.py
  -> agents/answer.py
```

## Knowledge Base Layers

The KB is intentionally split into five layers:

1. `data/kb/manifest.yaml` declares source locations.
2. `kb/catalog.py` reports source existence, size, authority, and build role.
3. `kb/*_*.py` loaders parse source files into `InternalChunk` records.
4. `kb/service.py` rebuilds the in-memory registry and chooses lexical or hybrid retrieval.
5. `agents/retrieval.py` applies business retrieval policy and trace generation.

The catalog layer is read-only. It does not change retrieval behavior; it makes
build status easier to inspect and test.

## Evidence Rules

- Official documents are primary policy evidence.
- Experience notes are useful but supplementary.
- Web results are supplementary and should not override official documents.
- Credibility metadata is attached before answer generation.
- Conflict hints should lower confidence in experience notes, not delete them.

## Delivery Hygiene

Keep these out of Git:

- `.env`
- `data/auth/`
- `data/chroma_db/`
- Python caches and pytest caches
- recordings and generated report output

Keep these in Git:

- source code
- tests
- public KB source files
- web product files
- docs and examples required for reproducible demos
