# RUC Baoyan Agent

A LangGraph-based agent project for students seeking recommendation-based admission to Renmin University of China.

## Environment Setup

1. Create a Python 3.11 virtual environment:
   `python3.11 -m venv .venv`
2. Activate the virtual environment first:
   - macOS: `source .venv/bin/activate`
   - Windows: `.venv\Scripts\activate`
3. Verify Python version in activated `.venv`:
   `python --version` (must be `Python 3.11.x`)
4. Install dependencies:
   `pip install -r requirements.txt`
5. Copy `.env.example` to `.env` and set your API keys.
6. Run:
   `python app.py`

> If you do not want to activate `.venv`, run directly:
> `.venv/bin/python app.py`

## Demo Run

`app.py` is the current one-command demo entry.

```bash
source .venv/bin/activate
python --version   # must be Python 3.11.x
python app.py
```

## Test

```bash
source .venv/bin/activate
python --version   # must be Python 3.11.x
python -m pytest -q
```

## Team Workflow

### Responsibility Split
- **Member 1 (Flow/Graph)**: `graph/`, `app.py`
- **Member 2 (Data/Retrieval)**: `tools/`, `agents/retrieval.py`, `data/mock_*.json`
- **Member 3 (Answer/Prompt/Test)**: `agents/answer.py`, `agents/demo.py`, `prompts/`, `tests/`

### High-Conflict Files (avoid editing together)
- `graph/builder.py`
- `graph/nodes.py`
- `app.py`
- `graph/state.py`

### Git Collaboration Rules
- Do not develop directly on `main`.
- Each member works on their own branch first:
  - `csj/dev`, `whd/dev`, `hx/dev`
- Merge changes through Pull Request only.
- Before opening PR, run:
  - `python app.py`
  - `python -m pytest -q`

For full collaboration details, read `TEAM_GUIDE.md`.
