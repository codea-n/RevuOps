# app/agents/graph.py
import logging
from langgraph.graph import StateGraph, END
from app.agents.state        import ReviewState
from app.agents.orchestrator import orchestrator_node
from app.agents.security_agent     import security_node
from app.agents.performance_agent  import performance_node
from app.agents.architecture_agent import architecture_node
from app.agents.supervisor_agent   import supervisor_node

logger = logging.getLogger(__name__)


def _should_continue(state: ReviewState) -> str:
    """
    Conditional edge: if the Orchestrator detected an error
    (e.g. empty diff), skip straight to END.
    Otherwise proceed to the specialist agents.
    """
    if state.get("error"):
        logger.warning(f"Graph: early exit — {state['error']}")
        return "end"
    return "continue"


def build_graph() -> StateGraph:
    graph = StateGraph(ReviewState)

    # --- Register nodes ---
    graph.add_node("orchestrator",   orchestrator_node)
    graph.add_node("security",       security_node)
    graph.add_node("performance",    performance_node)
    graph.add_node("architecture",   architecture_node)
    graph.add_node("supervisor",     supervisor_node)

    # --- Entry point ---
    graph.set_entry_point("orchestrator")

    # --- Conditional edge after Orchestrator ---
    # If empty diff → END, otherwise fan out to all three specialists
    graph.add_conditional_edges(
        "orchestrator",
        _should_continue,
        {
            "continue": "security",   # LangGraph fans to ALL nodes
            "end":      END,          # that share the same source
        },
    )

    # LangGraph runs security, performance, architecture in parallel
    # because they all share "orchestrator" as their source and none
    # depends on the others' output
    graph.add_edge("orchestrator", "performance")
    graph.add_edge("orchestrator", "architecture")

    # --- Converge: all three must finish before Supervisor runs ---
    graph.add_edge("security",     "supervisor")
    graph.add_edge("performance",  "supervisor")
    graph.add_edge("architecture", "supervisor")

    # --- Supervisor → END ---
    graph.add_edge("supervisor", END)

    return graph.compile()


# Module-level compiled graph — import this everywhere
review_graph = build_graph()