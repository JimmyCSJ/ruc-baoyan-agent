"""Compile long-plan LangGraph：hydrate → retrieve → 五段串行生成 → merge。"""



from langgraph.graph import END, START, StateGraph



from graph.long_plan_nodes import (

    generate_long_plan_part1,

    generate_long_plan_part2,

    generate_long_plan_part3,

    generate_long_plan_part4,

    generate_long_plan_part5,

    hydrate_long_plan,

    merge_long_plan,

    retrieve_long_plan_kb,

)

from graph.long_plan_state import LongPlanState





def build_long_plan_graph():

    g = StateGraph(LongPlanState)

    g.add_node("hydrate_long_plan", hydrate_long_plan)

    g.add_node("retrieve_long_plan_kb", retrieve_long_plan_kb)

    g.add_node("generate_long_plan_part1", generate_long_plan_part1)

    g.add_node("generate_long_plan_part2", generate_long_plan_part2)

    g.add_node("generate_long_plan_part3", generate_long_plan_part3)

    g.add_node("generate_long_plan_part4", generate_long_plan_part4)

    g.add_node("generate_long_plan_part5", generate_long_plan_part5)

    g.add_node("merge_long_plan", merge_long_plan)



    g.add_edge(START, "hydrate_long_plan")

    g.add_edge("hydrate_long_plan", "retrieve_long_plan_kb")

    g.add_edge("retrieve_long_plan_kb", "generate_long_plan_part1")

    g.add_edge("generate_long_plan_part1", "generate_long_plan_part2")

    g.add_edge("generate_long_plan_part2", "generate_long_plan_part3")

    g.add_edge("generate_long_plan_part3", "generate_long_plan_part4")

    g.add_edge("generate_long_plan_part4", "generate_long_plan_part5")

    g.add_edge("generate_long_plan_part5", "merge_long_plan")

    g.add_edge("merge_long_plan", END)

    return g.compile()

