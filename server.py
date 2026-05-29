"""HTTP server for quick Q&A interaction."""

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Tuple

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from auth.api import require_current_user, router as auth_router
from agents.long_plan import (
    empty_intake_template,
    empty_report_template,
    report_markdown_to_pdf_bytes,
    report_json_to_html,
    validate_intake,
)
from config import get_settings
from agents.retrieval import retrieve_documents_with_trace
from agents.router import classify_question
from graph.long_plan_builder import build_long_plan_graph
from graph.nodes import generate_answer, retrieve_docs, route_question
from graph.state import AgentState, QuestionType
from tools.xiaohongshu_excel_kb import kb_status, rebuild_kb


_long_plan_graph = None


def _get_long_plan_graph():
    global _long_plan_graph
    if _long_plan_graph is None:
        _long_plan_graph = build_long_plan_graph()
    return _long_plan_graph


class ChatRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    enable_web_search: bool = False
    kb_debug: bool = False
    kb_scope: Literal["hybrid", "official_only", "public_only"] = "hybrid"


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
    execution_steps: List[str] = Field(default_factory=list)
    official_files_read: List[str] = Field(default_factory=list)
    references: List[Dict[str, Any]] = Field(default_factory=list)


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
    kb_scope: Literal["hybrid", "official_only", "public_only"] = "hybrid"


class KBDebugTraceRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    enable_web_search: bool = False
    kb_scope: Literal["hybrid", "official_only", "public_only"] = "hybrid"


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


class ChatPDFRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    answer: str = Field(min_length=1)
    references: List[Dict[str, Any]] = Field(default_factory=list)


class WebAccessTestRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    scenario: Literal["official_site", "xhs_wechat_zhihu", "auto"] = "auto"
    force_fallback: bool = False


class ExamTutoringRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    enable_web_search: bool = False


class ExamTutoringResponse(BaseModel):
    answer: str
    question_type: Literal["exam_tutoring"] = "exam_tutoring"
    sources: List[dict]
    references: List[Dict[str, Any]] = Field(default_factory=list)
    execution_steps: List[str] = Field(default_factory=list)
    latency_ms: int


app = FastAPI(title="RUC Baoyan Agent API", version="0.1.0")


@app.exception_handler(Exception)
def unhandled_exception_handler(_request: Request, exc: Exception) -> JSONResponse:
    """Ensure API routes return JSON instead of plain 'Internal Server Error' text."""
    if isinstance(exc, HTTPException):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    detail = f"{type(exc).__name__}: {exc}"
    return JSONResponse(status_code=500, content={"detail": detail})


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(auth_router)
app.mount("/web", StaticFiles(directory="web"), name="web")


@app.get("/api/source/official")
def view_official_source(file: str) -> Response:
    """查看报告引用的本地官方材料文本。"""
    root = Path.cwd().resolve()
    target = (root / file).resolve()
    if root not in target.parents and target != root:
        raise HTTPException(status_code=400, detail="invalid source path")
    if not target.is_file() or target.suffix.lower() not in {".txt", ".md", ".pdf"}:
        raise HTTPException(status_code=404, detail="source file not found")
    if target.suffix.lower() == ".pdf":
        return FileResponse(target, media_type="application/pdf")
    text = target.read_text(encoding="utf-8", errors="ignore")
    return Response(content=text, media_type="text/plain; charset=utf-8")


def _build_initial_state(
    query: str,
    enable_web_search: bool = False,
    kb_debug: bool = False,
    kb_scope: Literal["hybrid", "official_only", "public_only"] = "hybrid",
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


def _chat_response_payload(
    state: AgentState,
    timing: Dict[str, int],
    *,
    debug: bool = False,
) -> Dict[str, Any]:
    trace = state.get("retrieval_trace") if debug else None
    references = state.get("references") or []
    return {
        "answer": state["final_answer"],
        "question_type": state["question_type"],
        "sources": state["retrieved_docs"],
        "latency_ms": timing["total_ms"],
        "timing": timing,
        "retrieval_trace": trace,
        "execution_steps": list(state.get("execution_steps") or []),
        "official_files_read": list(state.get("official_files_read") or []),
        "references": list(references),
    }


def _kb_debug_flag(payload: ChatRequest, header_val: Optional[str]) -> bool:
    if payload.kb_debug:
        return True
    if header_val is None:
        return False
    return header_val.strip().lower() in ("1", "true", "yes", "on")


@app.get("/")
def login_page() -> FileResponse:
    return FileResponse("web/login.html")


@app.get("/app")
def workspace() -> FileResponse:
    return FileResponse("web/index.html")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/api/chat", response_model=ChatResponse)
def chat(
    payload: ChatRequest,
    x_kb_debug: Optional[str] = Header(default=None, alias="X-KB-Debug"),
    _user: str = Depends(require_current_user),
) -> ChatResponse:
    query = payload.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="query cannot be empty")

    debug = _kb_debug_flag(payload, x_kb_debug)
    try:
        state, timing = _run_chat_pipeline(
            _build_initial_state(
                query,
                payload.enable_web_search,
                debug,
                payload.kb_scope,
            ),
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"{type(exc).__name__}: {exc}") from exc
    trace = state.get("retrieval_trace") if debug else None
    references = state.get("references") or []

    return ChatResponse(
        answer=state["final_answer"],
        question_type=state["question_type"],
        sources=state["retrieved_docs"],
        latency_ms=timing["total_ms"],
        timing=TimingBreakdown(**timing),
        retrieval_trace=trace,
        execution_steps=list(state.get("execution_steps") or []),
        official_files_read=list(state.get("official_files_read") or []),
        references=list(references),
    )


@app.post("/api/chat/stream")
def chat_stream(
    payload: ChatRequest,
    x_kb_debug: Optional[str] = Header(default=None, alias="X-KB-Debug"),
    _user: str = Depends(require_current_user),
) -> StreamingResponse:
    """NDJSON 流：推送快问快答各阶段进度，最后一行 stage=done 含完整回答。"""
    query = payload.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="query cannot be empty")
    debug = _kb_debug_flag(payload, x_kb_debug)

    def ndjson_gen():
        t_wall = time.perf_counter()
        try:
            state = _build_initial_state(
                query,
                payload.enable_web_search,
                debug,
                payload.kb_scope,
            )
            yield json.dumps(
                {"stage": "progress", "label": "正在分析问题类型与检索策略…", "pct": 10},
                ensure_ascii=False,
            ) + "\n"
            t0 = time.perf_counter()
            s1: AgentState = {**state, **route_question(state)}  # type: ignore[misc]
            route_ms = int((time.perf_counter() - t0) * 1000)
            yield json.dumps(
                {
                    "stage": "progress",
                    "label": "正在检索知识库（官方文件 / 公众经验）…",
                    "pct": 32,
                    "question_type": s1.get("question_type"),
                },
                ensure_ascii=False,
            ) + "\n"
            t1 = time.perf_counter()
            s2: AgentState = {**s1, **retrieve_docs(s1)}  # type: ignore[misc]
            retrieve_ms = int((time.perf_counter() - t1) * 1000)
            steps = list(s2.get("execution_steps") or [])
            files = list(s2.get("official_files_read") or [])
            label = "正在检索官方文件…" if files else "正在整理检索证据…"
            if payload.enable_web_search:
                label = "正在检索文件并补充联网线索…"
            yield json.dumps(
                {
                    "stage": "progress",
                    "label": label,
                    "pct": 58,
                    "execution_steps": steps[:10],
                    "official_files_read": files[:8],
                    "sources_count": len(s2.get("retrieved_docs") or []),
                },
                ensure_ascii=False,
            ) + "\n"
            yield json.dumps(
                {"stage": "progress", "label": "正在思考中，调用模型生成回答…", "pct": 82},
                ensure_ascii=False,
            ) + "\n"
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
            yield json.dumps(
                {
                    "stage": "done",
                    "label": "生成完成",
                    "pct": 100,
                    "data": _chat_response_payload(s3, timing, debug=debug),
                },
                ensure_ascii=False,
                default=str,
            ) + "\n"
        except Exception as exc:
            yield json.dumps({"stream_error": f"{type(exc).__name__}: {exc}"}) + "\n"

    return StreamingResponse(ndjson_gen(), media_type="application/x-ndjson")


@app.post("/api/chat/pdf")
def chat_pdf(
    payload: ChatPDFRequest,
    _user: str = Depends(require_current_user),
) -> Response:
    """Generate PDF from a quick Q&A answer with references and disclaimer."""
    from agents.long_plan import report_markdown_to_pdf_bytes

    q = payload.query.strip()
    answer = payload.answer.strip()
    refs = payload.references or []

    md_lines = [
        f"# 快问快答\n",
        f"## 问题\n{q}\n",
        f"## 回答\n{answer}\n",
    ]
    if refs:
        md_lines.append("## 参考文献\n")
        for r in refs:
            idx = r.get("index", "")
            entry = r.get("entry", "")
            md_lines.append(f"[{idx}] {entry}\n")
    md_lines.append("---\n")
    md_lines.append(
        "*免责声明：本回答由AI生成，带有网络溯源的内容提取自过往经验分享，仅供参考。"
        "最新招生要求请以人大陆续发布的官方文件为准。*\n"
    )

    md = "\n".join(md_lines)
    try:
        pdf_bytes = report_markdown_to_pdf_bytes(md)
    except RuntimeError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"pdf generation failed: {exc}") from exc

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": 'attachment; filename="ruc-baoyan-answer.pdf"',
        },
    )


@app.post("/api/exam-tutoring", response_model=ExamTutoringResponse)
def exam_tutoring(
    payload: ExamTutoringRequest,
    _user: str = Depends(require_current_user),
) -> ExamTutoringResponse:
    """笔试辅导：优先从公众经验库检索笔试科目、题型和备考重点。"""
    from agents.answer import generate_exam_tutoring_answer, generate_mock_answer
    from agents.retrieval import _enrich_web_docs
    from kb.service import search_experience_by_kb_groups, search_official

    q = payload.query.strip()
    if not q:
        raise HTTPException(status_code=400, detail="query cannot be empty")

    t0 = time.perf_counter()
    execution_steps: List[str] = []
    exam_query = f"{q} 笔试 科目 考什么 题型 考核 内容 备考 面试 夏令营 预推免"
    execution_steps.append("优先检索小红书/知乎经验库中的笔试科目、题型和备考内容。")
    experience_docs = search_experience_by_kb_groups(
        exam_query,
        28,
        {"public_info_xhs"},
    )
    execution_steps.append(f"经验库命中 {len(experience_docs)} 条资料。")
    execution_steps.append("补充检索官方文件，用于区分考研口径和推免口径。")
    official_docs = search_official(q, 4)
    execution_steps.append(f"官方文件命中 {len(official_docs)} 条资料。")
    docs = list(experience_docs) + list(official_docs)

    web_docs: List[dict] = []
    if payload.enable_web_search:
        execution_steps.append("已开启联网补充搜索，先尝试浏览器/网页通道，再使用普通搜索兜底。")
        from tools.web_access_bridge import search_web_via_web_access
        from tools.web_search import search_web_vertical

        web_raw, web_meta = search_web_via_web_access(f"{q} 笔试 经验 小红书 知乎")
        if web_raw:
            execution_steps.append(f"浏览器/网页通道命中 {len(web_raw)} 条网页资料。")
            web_docs = _enrich_web_docs(web_raw)
        else:
            reason = str(web_meta.get("failure_reason") or "未返回结果") if isinstance(web_meta, dict) else "未返回结果"
            execution_steps.append(f"浏览器/网页通道未命中：{reason}；改用普通搜索兜底。")
            web_docs = _enrich_web_docs(search_web_vertical(f"{q} 笔试 经验 小红书 知乎"))
            execution_steps.append(f"普通搜索兜底命中 {len(web_docs)} 条网页资料。")
        docs.extend(web_docs)
    else:
        execution_steps.append("本次未开启联网补充搜索，只使用本地知识库与官方文件。")

    prompt_query = (
        f"{q}\n\n"
        "请只围绕保研/夏令营/预推免笔试辅导回答：笔试科目、笔试内容、经验库提到的题型或重点、"
        "本周准备动作，以及哪些内容需要以学院当年通知为准。"
    )
    settings = get_settings()
    if settings.enable_real_llm:
        try:
            answer, refs = generate_exam_tutoring_answer(prompt_query, docs)
        except Exception:
            answer, refs = generate_mock_answer(
                user_query=prompt_query,
                question_type="experience_reference",
                retrieved_docs=docs,
            )
    else:
        answer, refs = generate_mock_answer(
            user_query=prompt_query,
            question_type="experience_reference",
            retrieved_docs=docs,
        )

    latency_ms = int((time.perf_counter() - t0) * 1000)
    return ExamTutoringResponse(
        answer=answer,
        sources=docs,
        references=refs,
        execution_steps=execution_steps,
        latency_ms=latency_ms,
    )


@app.get("/api/long-chat/templates")
def long_chat_templates() -> dict:
    return {
        "intake": empty_intake_template(),
        "report_skeleton": empty_report_template(),
    }


async def _long_plan_body_use_web(request: Request) -> Tuple[Dict[str, Any], bool]:
    """读取原始 JSON，避免旧版 Pydantic 模型强制要求 goal/intake 导致 422。"""
    try:
        raw = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=422, detail={"errors": [f"请求体不是合法 JSON：{exc}"]}) from exc
    if not isinstance(raw, dict):
        raise HTTPException(status_code=422, detail={"errors": ["请求体必须是 JSON 对象"]})
    data = dict(raw)
    use_web = bool(data.pop("use_web", True))
    return data, use_web


@app.post("/api/long-chat/report")
async def long_chat_report(
    request: Request,
    _user: str = Depends(require_current_user),
) -> dict:
    """表单 JSON → 校验 intake → LangGraph 初始状态 → 五段式报告 + Markdown。"""
    data, use_web = await _long_plan_body_use_web(request)
    ok, errors, intake = validate_intake(data)
    if not ok:
        raise HTTPException(status_code=422, detail={"errors": errors})

    t0 = time.perf_counter()
    state = {"intake": intake, "use_web": use_web}
    out = _get_long_plan_graph().invoke(state)
    latency_ms = int((time.perf_counter() - t0) * 1000)
    rep = out.get("report") or {}
    return {
        "report": rep,
        "report_markdown": out.get("report_markdown") or "",
        "retrieval_trace": out.get("retrieval_trace"),
        "latency_ms": latency_ms,
        "error": (out.get("error") or "").strip(),
        "generation": rep.get("_generation"),
        "fallback_reason": rep.get("_fallback_reason"),
        "references": out.get("references") or [],
        "retrieved_docs": out.get("retrieved_docs") or [],
    }


@app.post("/api/long-chat/report/stream")
async def long_chat_report_stream(
    request: Request,
    _user: str = Depends(require_current_user),
):
    """与 `/api/long-chat/report` 相同入参，NDJSON 流式推送每个 LangGraph 节点输出（便于前端分步展示）。"""
    data, use_web = await _long_plan_body_use_web(request)
    ok, errors, intake = validate_intake(data)
    if not ok:
        raise HTTPException(status_code=422, detail={"errors": errors})

    def ndjson_gen():
        graph = _get_long_plan_graph()
        init: Dict[str, Any] = {"intake": intake, "use_web": use_web}
        try:
            for step in graph.stream(init, stream_mode="updates"):
                yield json.dumps(step, ensure_ascii=False, default=str) + "\n"
        except Exception as exc:
            yield json.dumps({"stream_error": str(exc)}) + "\n"

    return StreamingResponse(ndjson_gen(), media_type="application/x-ndjson")


@app.post("/api/long-chat/report/pdf")
async def long_chat_report_pdf(
    request: Request,
    _user: str = Depends(require_current_user),
) -> Response:
    """返回 PDF。若请求体含非空 `report_markdown`，仅做 Markdown→PDF（秒级）；否则与 `/api/long-chat/report` 相同入参并重新跑整条生成链路。"""
    try:
        raw = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=422, detail={"errors": [f"请求体不是合法 JSON：{exc}"]}) from exc
    if not isinstance(raw, dict):
        raise HTTPException(status_code=422, detail={"errors": ["请求体必须是 JSON 对象"]})

    md_fast = raw.get("report_markdown")
    if isinstance(md_fast, str) and md_fast.strip():
        md = md_fast.strip()
        try:
            pdf_bytes = report_markdown_to_pdf_bytes(md)
        except RuntimeError as exc:
            raise HTTPException(status_code=501, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"pdf generation failed: {exc}") from exc
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": 'attachment; filename="ruc-baoyan-long-plan.pdf"',
            },
        )

    data = dict(raw)
    use_web = bool(data.pop("use_web", True))
    ok, errors, intake = validate_intake(data)
    if not ok:
        raise HTTPException(status_code=422, detail={"errors": errors})

    state = {"intake": intake, "use_web": use_web}
    out = _get_long_plan_graph().invoke(state)
    md = str(out.get("report_markdown") or "")
    if not md.strip():
        raise HTTPException(status_code=500, detail="empty report markdown")
    try:
        pdf_bytes = report_markdown_to_pdf_bytes(md)
    except RuntimeError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"pdf generation failed: {exc}") from exc

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": 'attachment; filename="ruc-baoyan-long-plan.pdf"',
        },
    )


@app.post("/api/long-chat/report/html")
async def long_chat_report_html(
    request: Request,
    _user: str = Depends(require_current_user),
) -> Response:
    """返回可直接打开的 HTML 报告；若请求体含 report_markdown 则不重新生成。"""
    from agents.long_plan import report_markdown_to_html

    try:
        raw = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=422, detail={"errors": [f"请求体不是合法 JSON：{exc}"]}) from exc
    if not isinstance(raw, dict):
        raise HTTPException(status_code=422, detail={"errors": ["请求体必须是 JSON 对象"]})

    as_download = bool(raw.get("download"))
    disposition = (
        'attachment; filename="ruc-baoyan-long-plan.html"'
        if as_download
        else 'inline; filename="ruc-baoyan-long-plan.html"'
    )

    report_fast = raw.get("report")
    if isinstance(report_fast, dict) and report_fast:
        refs_fast = raw.get("references")
        if isinstance(refs_fast, list) and refs_fast and not report_fast.get("_references"):
            report_fast = dict(report_fast)
            report_fast["_references"] = refs_fast
        html = report_json_to_html(report_fast)
        return Response(
            content=html,
            media_type="text/html; charset=utf-8",
            headers={"Content-Disposition": disposition},
        )

    md_fast = raw.get("report_markdown")
    if isinstance(md_fast, str) and md_fast.strip():
        html = report_markdown_to_html(md_fast.strip())
        return Response(
            content=html,
            media_type="text/html; charset=utf-8",
            headers={"Content-Disposition": disposition},
        )

    data = dict(raw)
    use_web = bool(data.pop("use_web", True))
    ok, errors, intake = validate_intake(data)
    if not ok:
        raise HTTPException(status_code=422, detail={"errors": errors})
    out = _get_long_plan_graph().invoke({"intake": intake, "use_web": use_web})
    rep = out.get("report") or {}
    if isinstance(rep, dict) and rep:
        html = report_json_to_html(rep)
        return Response(
            content=html,
            media_type="text/html; charset=utf-8",
            headers={"Content-Disposition": disposition},
        )
    md = str(out.get("report_markdown") or "")
    if not md.strip():
        raise HTTPException(status_code=500, detail="empty report markdown")
    html = report_markdown_to_html(md)
    return Response(
        content=html,
        media_type="text/html; charset=utf-8",
        headers={"Content-Disposition": disposition},
    )


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
