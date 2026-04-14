"""Official source retrieval.

Owner: member 2 (data & retrieval).
Responsibility: official-site mock retrieval.
Avoid putting graph orchestration or answer-generation logic here.
"""

from typing import List

from graph.state import RetrievedDoc
from tools.mock_data_loader import load_topic_docs


def search_official_for_major() -> List[RetrievedDoc]:
    return load_topic_docs("mock_official.json", "major_info")


def search_official_for_admission_requirement() -> List[RetrievedDoc]:
    return load_topic_docs("mock_official.json", "admission_requirement")


def search_official_for_eligibility_evaluation() -> List[RetrievedDoc]:
    return load_topic_docs("mock_official.json", "eligibility_evaluation")
