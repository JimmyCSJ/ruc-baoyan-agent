from graph.builder import build_graph


def main() -> None:
    graph = build_graph()

    user_query = "我想了解中国人民大学某学院有哪些专业，以及申请条件是什么？"
    initial_state = {
        "user_query": user_query,
        "question_type": "",
        "retrieved_docs": [],
        "final_answer": "",
        "chat_history": [],
    }

    result = graph.invoke(initial_state)

    print("=== Agent Demo Start ===")
    print(f"User Query: {result['user_query']}")
    print(f"Question Type: {result['question_type']}")
    print("Retrieved Docs:")
    for idx, doc in enumerate(result["retrieved_docs"], start=1):
        print(f"{idx}. [{doc['source']}] {doc['content']}")
    print("Final Answer:")
    print(result["final_answer"])
    print("=== Agent Demo End ===")


if __name__ == "__main__":
    main()
