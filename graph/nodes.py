from typing import Any, Dict, List

from agents.answer import generate_llm_answer
from graph.state import AgentState


def route_question(state: AgentState) -> Dict[str, str]:
    query = state["user_query"]

    if "经验" in query:
        question_type = "experience"
    elif "条件" in query or "成绩" in query:
        question_type = "requirements"
    elif "专业" in query:
        question_type = "major_info"
    else:
        question_type = "general"

    return {"question_type": question_type}


def retrieve_docs(state: AgentState) -> Dict[str, List[Dict[str, Any]]]:
    query = state["user_query"]
    question_type = state["question_type"]

    docs: List[Dict[str, Any]] = []

    if "专业" in query or question_type == "major_info":
        docs.extend(
            [
                {"source": "official_site", "content": "人大信息学院：计算机科学与技术、数据科学与大数据技术等专业方向。"},
                {"source": "brochure", "content": "人大统计学院：统计学、应用统计、数据分析相关培养方向。"},
            ]
        )

    if "条件" in query or "成绩" in query or question_type == "requirements":
        docs.extend(
            [
                {"source": "official_site", "content": "常见申请条件：绩点排名靠前、科研/竞赛经历、英语成绩达标。"},
                {"source": "brochure", "content": "部分学院关注数学与专业核心课成绩，并综合面试表现。"},
            ]
        )

    if "经验" in query or question_type == "experience":
        docs.extend(
            [
                {"source": "xiaohongshu", "content": "经验贴摘要：提前联系导师、尽早整理材料、模拟面试问题。"},
                {"source": "xiaohongshu", "content": "经验贴摘要：突出个人项目与研究兴趣匹配度。"},
            ]
        )

    if not docs:
        docs.append({"source": "fallback", "content": "未命中具体类别，建议先查看人大研招网与学院官网最新通知。"})

    return {"retrieved_docs": docs}


def generate_answer(state: AgentState) -> Dict[str, str]:
    docs = state["retrieved_docs"]
    try:
        answer = generate_llm_answer(
            user_query=state["user_query"],
            question_type=state["question_type"],
            retrieved_docs=docs,
        )
    except Exception:
        # 无 key 或调用失败时，回退到本地 mock，保证链路可演示
        lines = [f"- {doc['content']}" for doc in docs]
        answer = (
            f"基于你的问题“{state['user_query']}”，这是一个 mock 测试回答。\n"
            f"问题分类：{state['question_type']}\n"
            "参考信息：\n"
            + "\n".join(lines)
        )
    return {"final_answer": answer}
