"""Retrieval unit tests.

Owner: member 3.
"""

from agents.retrieval import retrieve_documents


def test_retrieve_major_docs() -> None:
    docs = retrieve_documents("我想看专业", "major_info")
    assert docs
    assert any(doc["source"] == "official_site" for doc in docs)


def test_retrieve_requirement_docs() -> None:
    docs = retrieve_documents("我想了解申请条件", "admission_requirement")
    assert docs
    assert any(doc["source"] == "brochure" for doc in docs)


def test_retrieve_experience_docs() -> None:
    docs = retrieve_documents("保研经验", "experience_reference")
    assert docs
    assert all("confidence" in doc for doc in docs)
