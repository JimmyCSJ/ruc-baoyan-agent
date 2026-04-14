"""Mock data loader.

Owner: member 2.
Responsibility: centralized data loading from `data/` for retrieval modules.
Avoid putting routing/answer logic here.
"""

import json
from pathlib import Path
from typing import List

from graph.state import RetrievedDoc

DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def load_topic_docs(filename: str, topic: str) -> List[RetrievedDoc]:
    with open(DATA_DIR / filename, "r", encoding="utf-8") as f:
        rows = json.load(f)
    docs: List[RetrievedDoc] = []
    for row in rows:
        if row.get("topic") != topic:
            continue
        docs.append(
            {
                "source": row["source"],
                "title": row["title"],
                "content": row["content"],
                "confidence": float(row["confidence"]),
            }
        )
    return docs
