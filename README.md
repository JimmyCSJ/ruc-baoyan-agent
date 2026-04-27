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
            -> official PDF index (kb/official_pdf.py)
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

打开 [http://127.0.0.1:8000](http://127.0.0.1:8000)。

## 常用接口

- `GET /health`：健康检查
- `POST /api/chat`：主问答
- `GET /api/kb/status`：知识库状态
- `POST /api/kb/rebuild`：重建 KB 索引
- `POST /api/kb/retrieve-preview`：仅检索调试（不走 LLM）

## 关键配置

- LLM：`DEEPSEEK_API_KEY`、`DEEPSEEK_BASE_URL`、`DEEPSEEK_MODEL`、`ENABLE_REAL_LLM`
- 大规模经验库召回：`KB_EXPERIENCE_TOP_K_XHS_ONLY`
- 上下文预算：`LLM_CONTEXT_MAX_CHARS`、`LLM_CONTEXT_DOC_MAX_CHARS` 等

## 测试

```bash
source .venv/bin/activate
python -m pytest -q
```
