# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

RUC 保研问答 Agent — a LangGraph-based RAG system that answers questions about 人大 (Renmin University) graduate admission via 保研/推免. It retrieves from three sources (official brochures, 小红书 experience notes in Excel, optional web search) and generates structured Chinese-language answers.

## Commands

```bash
# Start the FastAPI server
python -m uvicorn server:app --host 127.0.0.1 --port 8000

# Run CLI demo (no server needed)
python app.py

# Run all tests
python -m pytest -q

# Run a specific test file
python -m pytest tests/test_retrieval.py -q

# Rebuild KB indexes at startup
python -c "from kb.service import rebuild_all; rebuild_all()"
```

## Architecture

**Entry points**: `server.py` (FastAPI, production) and `app.py` (CLI demo). Both invoke the same LangGraph pipeline.

**Main pipeline** (`graph/builder.py`): A 3-node linear LangGraph:
1. `route_question` — keyword classifier → `QuestionType` (one of: `major_info`, `admission_requirement`, `eligibility_evaluation`, `experience_reference`, `general_info`)
2. `retrieve_docs` — staged retrieval with trace (official → experience → optional web)
3. `generate_answer` — sends packed context to LLM (mock answer when `ENABLE_REAL_LLM=false`)

**Long-plan pipeline** (`graph/long_plan_builder.py`): A 9-node graph for 五段式报告 generation: `hydrate → retrieve → part1..part5 (serial) → merge`. Exposed at `/api/long-chat/report`.

**Graph nodes** (`graph/nodes.py`) are thin adapters that call agent modules and map return values into `AgentState`. Business logic lives in `agents/`.

**State schema** (`graph/state.py`): `AgentState` TypedDict with `user_query`, `question_type`, `retrieved_docs`, `final_answer`, `chat_history`, `enable_web_search`, `kb_scope`, retrieval trace fields, and debug flags.

## Knowledge base (kb/)

The KB is an in-memory singleton (`KBRegistry` in `kb/registry.py`) with thread-safe locking. It holds two chunk lists: `official` and `experience`.

- **Loading**: `kb/service.py` → `rebuild_all()` parses data sources defined in `data/kb/manifest.yaml`:
  - `official_documents_brochures/` — pre-extracted TXT from 36 official PDF 招生简章
  - `public_info_xhs/小红书保研笔记.xlsx` — crowdsourced experience notes
  - `public_info_manual_stats/ruc_2026_manual_stats.txt` — hand-compiled admission stats

- **Scoring** (`kb/service.py`, `kb/hybrid_search.py`): hybrid retrieval is the default path when available (ChromaDB dense vectors + BM25 + RRF). If vector/BM25 setup fails, search falls back to lexical matching (`kb/scoring.py`) so the app remains usable.

- **Retrieval** (`agents/retrieval.py`): Staged with top-k per source. Official files are selected via LLM from `filenames.txt`, not by lexical scoring alone. Has fallback + boost logic (`KB_MANUAL_STATS_TOP_K`, `KB_WEAK_FALLBACK_XHS_TOP_K`). The `force_comprehensive` env flag defaults to true, always running broad cross-source retrieval.

## Credibility system (tools/credibility.py)

Every retrieved doc gets annotated with heuristic fields defined in `tools/credibility.py`:
- `source_type`: `official_school_document` | `experience_note` | `web_citation` | `other`
- `credibility_level`: `high` | `medium` | `low`
- `suspected_ad`: regex-based detection of marketing/redirect/unrealistic language
- `freshness`: year-based and source-based hints
- `evidence_role`: `primary_policy` | `supplementary_experience` | `supplementary_web`

`enrich_experience_against_official()` runs conflict detection between experience notes and official chunks, appending `ad_risk_reasons` when inconsistencies are found. Official school documents always override experience notes in the answer prompt.

## LLM configuration

Configured via `config.py` (reads `.env`). Supports Moark-compatible API and DeepSeek API (二选一: `MOARK_API_KEY`/`MOARK_BASE_URL` or `DEEPSEEK_API_KEY`/`DEEPSEEK_BASE_URL`). The `ENABLE_REAL_LLM=true` flag is required to use real LLM calls; without it, answers are mock template placeholders.

Key env vars: `LLM_CONTEXT_MAX_CHARS`, `LLM_CONTEXT_DOC_MAX_CHARS`, and per-group doc limits control context packing in `agents/answer.py` → `_select_docs_for_llm()`.

## Web access

Two-tier web retrieval in `agents/retrieval.py`:
1. Primary: CDP-based web access via `tools/web_access_bridge.py`
2. Fallback: DuckDuckGo via `tools/web_search.py`

## Key API endpoints (server.py)

- `POST /api/chat` — main Q&A
- `POST /api/long-chat/report` — long-form five-section report
- `GET /api/kb/status` — KB stats
- `POST /api/kb/rebuild` — rebuild in-memory indexes
- `POST /api/kb/retrieve-preview` — retrieval-only debug (no LLM)
- `POST /api/kb/xiaohongshu/verify` — diagnostic for 小红书 KB quality
- `POST /api/kb/official/verify` — diagnostic for official PDF KB quality
- `POST /api/web-access/test` — web access primary vs fallback behavior test

## Testing

Tests in `tests/` use pytest. No database or external service mocks — tests run against the real in-memory KB (which auto-rebuilds on first access). Key test files: `test_retrieval.py` (KB retrieval quality), `test_answer.py` (LLM answer format), `test_server_api.py` (HTTP endpoint integration), `test_credibility.py` (ad-risk detection heuristics).
