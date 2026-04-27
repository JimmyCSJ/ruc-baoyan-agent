"""HTTP server for quick Q&A interaction."""

import time
from typing import Any, Dict, List, Literal, Optional, Tuple

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from agents.long_plan import (
    empty_intake_template,
    empty_report_template,
    generate_clarifying_questions,
    generate_plan_report,
)
from config import get_settings
from agents.retrieval import retrieve_documents_with_trace
from agents.router import classify_question
from graph.nodes import generate_answer, retrieve_docs, route_question
from graph.state import AgentState, QuestionType
from tools.xiaohongshu_excel_kb import kb_status, rebuild_kb


class ChatRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    enable_web_search: bool = False
    kb_debug: bool = False
    kb_scope: Literal["hybrid", "official_only", "xiaohongshu_only"] = "hybrid"


class TimingBreakdown(BaseModel):
    route_ms: int
    retrieve_ms: int
    answer_ms: int
    total_ms: int


class ChatResponse(BaseModel):
    answer: str
    question_type: QuestionType
    sources: List[dict]
    latency_ms: int
    timing: TimingBreakdown
    retrieval_trace: Optional[Dict[str, Any]] = None


class KBStatusResponse(BaseModel):
    loaded: bool
    row_count: int
    loaded_at: str
    checksum: str
    path: str
    official_chunk_count: int = 0
    experience_chunk_count: int = 0
    rebuild_digest: str = ""
    kb_groups: List[Dict[str, Any]] = Field(default_factory=list)


class RetrievePreviewRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    enable_web_search: bool = False
    kb_scope: Literal["hybrid", "official_only", "xiaohongshu_only"] = "hybrid"


class KBDebugTraceRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    enable_web_search: bool = False
    kb_scope: Literal["hybrid", "official_only", "xiaohongshu_only"] = "hybrid"


class XiaohongshuVerifyRequest(BaseModel):
    """Excel KB quality: row counts, samples, lexical match trace, optional row diagnosis."""

    query: str = Field(default="", max_length=2000)
    top_k: int = Field(8, ge=1, le=64)
    check_excel_row: Optional[int] = Field(default=None, ge=1, le=1_000_000)
    sample_count: int = Field(5, ge=1, le=20)


class OfficialPDFVerifyRequest(BaseModel):
    sample_chunks_per_pdf: int = Field(3, ge=1, le=10)
    top_k_per_question: int = Field(5, ge=1, le=20)


class CredibilityEvalRequest(BaseModel):
    source_group: Literal["official", "experience", "web", "other"] = "experience"
    source_tag: str = "xiaohongshu_excel"
    title: str = ""
    text: str = ""
    provenance: Dict[str, Any] = Field(default_factory=dict)


class WebAccessTestRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    scenario: Literal["official_site", "xhs_wechat_zhihu", "auto"] = "auto"
    force_fallback: bool = False


class LongClarifyRequest(BaseModel):
    goal: str = Field(min_length=1, max_length=4000)
    partial_intake: Dict[str, Any] | None = None


class LongReportRequest(BaseModel):
    goal: str = Field(min_length=1, max_length=4000)
    intake: Dict[str, Any]
    use_web: bool = True


app = FastAPI(title="RUC Baoyan Agent API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/web", StaticFiles(directory="web"), name="web")


def _build_initial_state(
    query: str,
    enable_web_search: bool = False,
    kb_debug: bool = False,
    kb_scope: Literal["hybrid", "official_only", "xiaohongshu_only"] = "hybrid",
) -> AgentState:
    state: AgentState = {
        "user_query": query,
        "question_type": "general_info",
        "retrieved_docs": [],
        "final_answer": "",
        "chat_history": [],
        "enable_web_search": enable_web_search,
        "kb_scope": kb_scope,
    }
    if kb_debug:
        state["kb_debug"] = True
    return state


def _run_chat_pipeline(state: AgentState) -> Tuple[AgentState, Dict[str, int]]:
    t_wall = time.perf_counter()
    t0 = time.perf_counter()
    s1: AgentState = {**state, **route_question(state)}  # type: ignore[misc]
    route_ms = int((time.perf_counter() - t0) * 1000)
    t1 = time.perf_counter()
    s2: AgentState = {**s1, **retrieve_docs(s1)}  # type: ignore[misc]
    retrieve_ms = int((time.perf_counter() - t1) * 1000)
    t2 = time.perf_counter()
    s3: AgentState = {**s2, **generate_answer(s2)}  # type: ignore[misc]
    answer_ms = int((time.perf_counter() - t2) * 1000)
    total_ms = int((time.perf_counter() - t_wall) * 1000)
    timing = {
        "route_ms": route_ms,
        "retrieve_ms": retrieve_ms,
        "answer_ms": answer_ms,
        "total_ms": total_ms,
    }
    return s3, timing


def _kb_debug_flag(payload: ChatRequest, header_val: Optional[str]) -> bool:
    if payload.kb_debug:
        return True
    if header_val is None:
        return False
    return header_val.strip().lower() in ("1", "true", "yes", "on")


@app.get("/")
def index() -> FileResponse:
    return FileResponse("web/index.html")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/api/chat", response_model=ChatResponse)
def chat(
    payload: ChatRequest,
    x_kb_debug: Optional[str] = Header(default=None, alias="X-KB-Debug"),
) -> ChatResponse:
    query = payload.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="query cannot be empty")

    debug = _kb_debug_flag(payload, x_kb_debug)
    state, timing = _run_chat_pipeline(
        _build_initial_state(
            query,
            payload.enable_web_search,
            debug,
            payload.kb_scope,
        ),
    )
    trace = state.get("retrieval_trace") if debug else None

    return ChatResponse(
        answer=state["final_answer"],
        question_type=state["question_type"],
        sources=state["retrieved_docs"],
        latency_ms=timing["total_ms"],
        timing=TimingBreakdown(**timing),
        retrieval_trace=trace,
    )


@app.get("/api/long-chat/templates")
def long_chat_templates() -> dict:
    return {
        "intake": empty_intake_template(),
        "report_skeleton": empty_report_template(),
    }


@app.post("/api/long-chat/clarify")
def long_chat_clarify(payload: LongClarifyRequest) -> dict:
    return generate_clarifying_questions(payload.goal.strip(), payload.partial_intake)


@app.post("/api/long-chat/report")
def long_chat_report(payload: LongReportRequest) -> dict:
    t0 = time.perf_counter()
    report = generate_plan_report(
        payload.goal.strip(),
        payload.intake,
        use_web=payload.use_web,
    )
    latency_ms = int((time.perf_counter() - t0) * 1000)
    return {"report": report, "latency_ms": latency_ms}


@app.get("/api/kb/status", response_model=KBStatusResponse)
def get_kb_status() -> KBStatusResponse:
    return KBStatusResponse(**kb_status())


@app.post("/api/kb/retrieve-preview")
def kb_retrieve_preview(payload: RetrievePreviewRequest) -> dict:
    """Run routing + staged KB retrieval only (no LLM). Always returns verbose `retrieval_trace`."""
    q = payload.query.strip()
    qt = classify_question(q)
    docs, trace = retrieve_documents_with_trace(
        q,
        qt,
        payload.enable_web_search,
        kb_debug=True,
        kb_scope=payload.kb_scope,
    )
    return {
        "question_type": qt,
        "retrieval_trace": trace,
        "sources_count": len(docs),
        "sources": docs,
    }


@app.post("/api/kb/rebuild", response_model=KBStatusResponse)
def rebuild_kb_cache() -> KBStatusResponse:
    try:
        return KBStatusResponse(**rebuild_kb())
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/admin/kb/inspect")
def admin_kb_inspect() -> dict:
    if not get_settings().enable_kb_admin:
        raise HTTPException(status_code=404, detail="Not found")
    from kb.service import get_inspect_snapshot

    return get_inspect_snapshot()


@app.get("/api/kb/debug")
def kb_debug_bundle() -> dict:
    """Aggregated KB parse stats + samples + manifest paths (requires admin)."""
    if not get_settings().enable_kb_admin:
        raise HTTPException(status_code=404, detail="Not found")
    from kb.service import get_inspect_snapshot, get_legacy_aggregate_status

    return {
        "status": get_legacy_aggregate_status(),
        "inspect": get_inspect_snapshot(),
    }


@app.post("/api/kb/xiaohongshu/verify")
def xiaohongshu_kb_verify(payload: XiaohongshuVerifyRequest) -> dict:
    """Visible test flow for 小红书保研笔记.xlsx: counts, samples, matched rows + why, row diagnosis."""
    from kb.experience_verify import build_xiaohongshu_verify_report

    return build_xiaohongshu_verify_report(
        query=payload.query.strip(),
        top_k=payload.top_k,
        check_excel_row=payload.check_excel_row,
        sample_count=payload.sample_count,
    )


@app.post("/api/kb/official/verify")
def official_pdfs_verify(payload: OfficialPDFVerifyRequest) -> dict:
    """Verify official finance PDFs: chunk counts, samples, official_only retrieval traces."""
    from kb.official_verify import build_official_pdfs_verify_report

    return build_official_pdfs_verify_report(
        sample_chunks_per_pdf=payload.sample_chunks_per_pdf,
        top_k_per_question=payload.top_k_per_question,
    )


@app.post("/api/credibility/eval")
def credibility_eval(payload: CredibilityEvalRequest) -> dict:
    """Evaluate ad-risk/credibility fields on a concrete text example."""
    from tools.credibility import build_credibility_fields, credibility_impact_note

    fields = build_credibility_fields(
        source_group=payload.source_group,
        source_tag=payload.source_tag,
        title=payload.title,
        text=payload.text,
        provenance=payload.provenance,
    )
    impact = credibility_impact_note(
        source_group=payload.source_group,
        suspected_ad=bool(fields.get("suspected_ad", False)),
        credibility_level=str(fields.get("credibility_level", "")),
    )
    return {"fields": fields, "impact": impact}


@app.post("/api/web-access/test")
def web_access_test(payload: WebAccessTestRequest) -> dict:
    """Visible UI test: web-access primary vs fallback behavior."""
    from tools.web_access_bridge import search_web_via_web_access
    from tools.web_search import search_web_vertical

    q = payload.query.strip()
    if payload.scenario == "official_site":
        q = f"{q} site:ruc.edu.cn"
    elif payload.scenario == "xhs_wechat_zhihu":
        q = f"{q} 小红书 知乎 微信公众号"

    primary_docs, primary_meta = search_web_via_web_access(q)
    used_fallback = payload.force_fallback or not primary_docs
    fallback_docs: List[dict] = []
    final_docs = list(primary_docs)
    if used_fallback:
        fallback_docs = search_web_vertical(q)
        if fallback_docs:
            final_docs = fallback_docs

    return {
        "query": q,
        "scenario": payload.scenario,
        "web_access_primary": {
            "used": bool(primary_meta.get("used", False)),
            "failure_reason": str(primary_meta.get("failure_reason", "") or ""),
            "docs_count": len(primary_docs),
            "docs": primary_docs,
        },
        "fallback": {
            "used": used_fallback,
            "forced": payload.force_fallback,
            "docs_count": len(fallback_docs),
            "docs": fallback_docs,
        },
        "final_path": "fallback_web_search" if used_fallback and fallback_docs else "web_access_primary",
        "final_docs_count": len(final_docs),
        "final_docs": final_docs,
    }


@app.post("/api/kb/debug/trace")
def kb_debug_trace(payload: KBDebugTraceRequest) -> dict:
    """Verbose retrieval trace for debugging (requires admin)."""
    if not get_settings().enable_kb_admin:
        raise HTTPException(status_code=404, detail="Not found")
    q = payload.query.strip()
    qt = classify_question(q)
    docs, trace = retrieve_documents_with_trace(
        q,
        qt,
        payload.enable_web_search,
        kb_debug=True,
        kb_scope=payload.kb_scope,
    )
    return {
        "question_type": qt,
        "retrieval_trace": trace,
        "sources_count": len(docs),
        "sources": docs,
    }
