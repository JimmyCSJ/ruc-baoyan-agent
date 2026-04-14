"""Experience-post retrieval.

Owner: member 2 (data & retrieval).
Responsibility: experience-reference mock retrieval.
Avoid putting graph orchestration or answer-generation logic here.
"""

from typing import List

from graph.state import RetrievedDoc
from tools.mock_data_loader import load_topic_docs


def search_xiaohongshu_experience_reference() -> List[RetrievedDoc]:
    return load_topic_docs("mock_xiaohongshu.json", "experience_reference")
