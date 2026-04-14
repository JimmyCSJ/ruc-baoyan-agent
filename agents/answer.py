from typing import Any, Dict, List

from langchain_openai import ChatOpenAI

from config import get_settings


def generate_llm_answer(user_query: str, question_type: str, retrieved_docs: List[Dict[str, Any]]) -> str:
    settings = get_settings()
    if not settings.deepseek_api_key:
        raise ValueError("DEEPSEEK_API_KEY is not set.")

    context = "\n".join([f"- [{doc['source']}] {doc['content']}" for doc in retrieved_docs])
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
