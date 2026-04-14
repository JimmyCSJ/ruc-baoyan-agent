from graph.builder import build_graph


def main() -> None:
    graph = build_graph()
    print(f"Graph built successfully: {graph!r}")


if __name__ == "__main__":
    main()
