# TEAM_GUIDE

This file is the team-level collaboration guide for `ruc-baoyan-agent`.

## 1. Architecture Overview

Current project keeps a lightweight, modular structure:

- `graph/`: LangGraph workflow definition (state, node adapters, builder)
- `agents/`: business logic modules (router, retrieval, answer, demo rendering)
- `tools/`: data-source retrieval implementations
- `data/`: centralized mock datasets (JSON)
- `prompts/`: prompt text assets
- `tests/`: end-to-end + module unit tests

## 2. Module Boundaries

- `graph/*` should orchestrate only (no heavy business logic).
- `agents/router.py` should classify question type only.
- `agents/retrieval.py` should select tools and assemble docs only.
- `agents/answer.py` should generate output text only.
- `tools/*` should load/query source data only.
- `prompts/*` and `tests/*` are owned by answer/test role.

## 3. Suggested Ownership

- **Member 1 (Flow/Graph)**:
  - `graph/builder.py`
  - `graph/nodes.py`
  - `graph/state.py`
  - `app.py`
- **Member 2 (Data/Retrieval)**:
  - `agents/retrieval.py`
  - `tools/*.py`
  - `data/mock_*.json`
- **Member 3 (Answer/Prompt/Test)**:
  - `agents/answer.py`
  - `agents/demo.py`
  - `prompts/*.txt`
  - `tests/*.py`

## 4. High-Conflict Files

Try not to edit these files in parallel:

- `graph/nodes.py`
- `graph/builder.py`
- `graph/state.py`
- `app.py`

If two members must edit the same high-conflict file, sync in group chat first.

## 5. Branch Naming

- Long-lived branches:
  - `csj/dev`
  - `whd/dev`
  - `hx/dev`
- Optional feature/fix branches:
  - `csj/feature-xxx`
  - `whd/fix-xxx`
  - `hx/feature-xxx`

Never develop directly on `main`.

## 6. Suggested Development Order

1. Member 1 stabilizes graph/state contracts.
2. Member 2 updates data + retrieval logic and tool outputs.
3. Member 3 improves prompt/answer style and adds tests.
4. Run demo and tests before PR merge.

## 7. New Teammate Onboarding

Read in this order:

1. `README.md`
2. `TEAM_GUIDE.md`
3. `graph/state.py` (shared schema contract)
4. your owned module area

## 8. Run and Test Commands

Always use Python 3.11 venv.

- macOS activate:
  - `source .venv/bin/activate`
- Windows activate:
  - `.venv\Scripts\activate`
- verify:
  - `python --version` (must be `Python 3.11.x`)

Demo:

```bash
python app.py
```

Tests:

```bash
python -m pytest -q
```
