"""Brochure source retrieval.

Owner: member 2 (data & retrieval).
Responsibility: brochure mock retrieval.
Avoid putting graph orchestration or answer-generation logic here.
"""

from typing import List

from graph.state import RetrievedDoc
from tools.mock_data_loader import load_topic_docs


def search_brochure_for_major() -> List[RetrievedDoc]:
    return load_topic_docs("mock_brochure.json", "major_info")


def search_brochure_for_admission_requirement() -> List[RetrievedDoc]:
    return load_topic_docs("mock_brochure.json", "admission_requirement")
