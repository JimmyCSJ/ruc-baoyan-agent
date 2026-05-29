# RUC Baoyan Agent

面向人大保研问答场景的轻量 Agent。核心能力是：**官方 PDF + 小红书 Excel 经验库 + 可选联网检索**，并通过 LangGraph 串联路由、检索、回答。

## 30 秒看懂

- **入口**：`server.py`（HTTP）和 `app.py`（CLI）。
- **主链路**：`graph/nodes.py` -> `agents/router.py` -> `agents/retrieval.py` -> `agents/answer.py`。
- **知识库核心**：`kb/`（官方 PDF 解析、Excel 解析、索引、打分、检索）。
- **前端**：`web/`（单页 UI）。
- **测试**：`tests/`（检索、回答、API、可信度、KB 诊断）。

## 真实架构（当前主路径）

```text
User/Web
  -> server.py /api/chat
     -> route_question (agents/router.py)
     -> retrieve_documents_with_trace (agents/retrieval.py)
         -> kb/service.py
            -> official brochure index (kb/official_brochures.py)
            -> xiaohongshu Excel index (kb/experience_excel.py)
         -> optional web fallback (tools/web_access_bridge.py + tools/web_search.py)
     -> generate_llm_answer / generate_mock_answer (agents/answer.py)
```

## 目录导航（只列关键）

```text
.
├── server.py                  # FastAPI 主入口
├── app.py                     # CLI 入口
├── config.py                  # 环境变量设置
├── agents/                    # 业务层：路由/检索/回答/长问答
├── graph/                     # 编排层：状态与节点
├── kb/                        # 知识库核心实现
├── tools/                     # 外部能力适配（web、可信度、兼容入口）
├── web/                       # UI
├── tests/                     # pytest
├── data/kb/manifest.yaml      # KB 清单
└── 小红书保研笔记.xlsx         # 经验数据源
```

## 快速启动

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python -m uvicorn server:app --host 127.0.0.1 --port 8000
```

打开 [http://127.0.0.1:8000](http://127.0.0.1:8000) 注册/登录后进入工作台 [http://127.0.0.1:8000/app](http://127.0.0.1:8000/app)。各账户的保研个人信息保存在服务端 `data/auth/`（可用 `AUTH_DATA_DIR` 自定义路径）。

## 常用接口

- `GET /health`：健康检查
- `POST /api/chat`：主问答
- `POST /api/exam-tutoring`：笔试辅导（小红书经验库优先）
- `POST /api/long-chat/report/html`：生成可打开的 HTML 报告
- `GET /api/kb/status`：知识库状态
- `POST /api/kb/rebuild`：重建 KB 索引
- `POST /api/kb/retrieve-preview`：仅检索调试（不走 LLM）

## 关键配置

- LLM：`MOARK_API_KEY` 或 `DEEPSEEK_API_KEY`（二选一）、`MOARK_BASE_URL` 或 `DEEPSEEK_BASE_URL`、`MOARK_MODEL`；**必须** `ENABLE_REAL_LLM=true` 才会走真实模型（仅有 Key 不够）。
- 长程规划为 **五段分块生成**：单段 `max_tokens` 取 `min(LONG_PLAN_PART_MAX_TOKENS, LONG_PLAN_PART_OUTPUT_CEILING)`（默认 3072 与 4096），**不会**再与全局 `LLM_MAX_TOKENS` 取较大值，以免单次请求过大。HTTP 读超时见 `LONG_PLAN_LLM_TIMEOUT_S`。占位或网络错误时预览 Markdown 顶部会有说明。
- 默认检索：`ENABLE_HYBRID_SEARCH=true` 时使用向量 + BM25 混合检索；构建失败会自动回退到关键词检索。
- 仅公众信息库大规模召回：`KB_PUBLIC_TOP_K_PUBLIC_ONLY`
- 检索补强：`KB_MANUAL_STATS_TOP_K`（并入 `ruc_2026_manual_stats.txt` 条数上限，默认 14）、`KB_WEAK_FALLBACK_XHS_TOP_K`（命中偏弱时扩大小红书条数，默认 64）
- 上下文预算：`LLM_CONTEXT_MAX_CHARS`、`LLM_CONTEXT_DOC_MAX_CHARS` 等

## 测试

```bash
source .venv/bin/activate
python -m pytest -q
```
