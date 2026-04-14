# RUC Baoyan Agent

A LangGraph-based agent project for students seeking recommendation-based admission to Renmin University of China.

## Local setup

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

> If you do not want to activate `.venv`, you can run directly:
> `.venv/bin/python app.py`
