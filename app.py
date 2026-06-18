"""Demo application entrypoint.

Owner: member 1.
Responsibility: run graph workflow and call demo renderer.
Avoid placing detailed business logic here.
"""

from graph.builder import build_graph
from agents.demo import build_initial_state, default_demo_query, render_demo_output


def main() -> None:
    # Owner: member 1 maintains app entry and flow wiring.
    # Demo rendering is delegated to agents/demo.py (member 3).
    graph = build_graph()
    initial_state = build_initial_state(default_demo_query())
    result = graph.invoke(initial_state)
    print(render_demo_output(result))


if __name__ == "__main__":
    main()
