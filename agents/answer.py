"""Answer generation module.

Owner: member 3 (answer quality, prompts, output format, tests).
Responsibility: render answer text from state + prompt strategy.
Avoid putting retrieval source-selection logic here.
"""

from typing import List

from langchain_openai import ChatOpenAI

from config import get_settings
from graph.state import QuestionType, RetrievedDoc


def generate_llm_answer(user_query: str, question_type: QuestionType, retrieved_docs: List[RetrievedDoc]) -> str:
    settings = get_settings()
    if not settings.deepseek_api_key:
        raise ValueError("DEEPSEEK_API_KEY is not set.")

    context = "\n".join(
        [f"- [{doc['source']}|{doc['title']}|confidence={doc['confidence']}] {doc['content']}" for doc in retrieved_docs]
    )
    prompt = (
        "你是一个保研咨询助手，请基于给定资料回答用户问题。\n"
        "要求：\n"
        "1. 信息简洁、准确。\n"
        "2. 如果资料不足，明确提示用户以官网最新通知为准。\n"
        f"问题分类：{question_type}\n"
        f"用户问题：{user_query}\n"
        f"资料：\n{context}\n"
    )

    llm = ChatOpenAI(
        model=settings.deepseek_model,
        api_key=settings.deepseek_api_key,
        base_url=settings.deepseek_base_url,
        temperature=0.2,
    )
    return llm.invoke(prompt).content


def generate_mock_answer(user_query: str, question_type: QuestionType, retrieved_docs: List[RetrievedDoc]) -> str:
    lines = [f"- [{doc['title']}] {doc['content']}" for doc in retrieved_docs]
    return (
        f"基于你的问题“{user_query}”，这是一个 mock 测试回答。\n"
        f"问题分类：{question_type}\n"
        "参考信息：\n"
        + "\n".join(lines)
    )
