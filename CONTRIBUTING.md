# Contributing Guide

This project is maintained by a 3-person team:
- `csj` = chenshaojin
- `whd` = wanghaodi
- `hx` = huangxin

The goal of this guide is to keep collaboration simple, stable, and low-risk.

## 1) Branch Strategy

### Protected stable branch
- `main`: always keep this branch stable and runnable.
- Do **not** develop directly on `main`.

### Personal long-lived branches
- `csj/dev`
- `whd/dev`
- `hx/dev`

Each member should do normal development on their own `*/dev` branch.

### Optional feature branches
For larger changes, create short-lived branches from your own `*/dev` branch:
- `<id>/feature-xxx`
- `<id>/fix-xxx`

Examples:
- `csj/feature-retrieval`
- `whd/fix-router-bug`

## 2) Local Environment Rule (Required)

This project must run in the Python 3.11 virtual environment.

Before running code:

1. Activate venv
   - macOS:
     ```bash
     source .venv/bin/activate
     ```
   - Windows:
     ```powershell
     .venv\Scripts\activate
     ```
2. Verify version:
   ```bash
   python --version
   ```
   It must be `Python 3.11.x`.
3. Run project/test commands only after activation.

If you prefer not to activate manually, use:
```bash
.venv/bin/python app.py
```

## 3) Daily Development Workflow

### A. Start work
```bash
git checkout <your-dev-branch>
git pull origin <your-dev-branch>
```

### B. Develop and self-test
```bash
python app.py
```

### C. Commit and push
```bash
git add .
git commit -m "Short clear message"
git push origin <your-dev-branch>
```

## 4) Merge to Main

When your change is stable:
1. Ensure local run passes (`python app.py` in `.venv`).
2. Open a Pull Request to `main` from your branch.
3. Ask at least one teammate for a quick review.
4. Merge only after checks pass.

## 5) Commit Message Guideline

Use short, clear, action-based messages:
- `Add mock retrieval node`
- `Integrate DeepSeek answer generation`
- `Fix app entrypoint output format`
- `Update README and env setup`

## 6) Conflict Prevention Rules

1. Never commit secrets.
   - `.env` must stay local (already ignored).
2. If you modify shared core files (`app.py`, `graph/builder.py`, `graph/nodes.py`), announce in group chat first.
3. Before large merges, sync latest `main`:
   ```bash
   git checkout main
   git pull origin main
   ```

## 7) Optional: Create Your Dev Branch (First Time)

Example for `csj`:
```bash
git checkout main
git pull origin main
git checkout -b csj/dev
git push -u origin csj/dev
```

