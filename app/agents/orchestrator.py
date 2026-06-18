# app/agents/orchestrator.py
import logging
from app.agents.state import ReviewState

logger = logging.getLogger(__name__)


def orchestrator_node(state: ReviewState) -> dict:
    """
    Entry point of the graph.
    Validates the incoming state and logs what we're about to review.
    Returns only the keys it wants to update — LangGraph merges this
    into the full state automatically.
    """
    pr = state.get("pr_number", "unknown")
    repo = state.get("repo_full_name", "unknown")
    diff_len = len(state.get("diff", "").strip())
    logger.info(f"Orchestrator: starting review for PR #{pr} in {repo}")
    logger.info(f"Diff size: {diff_len} chars")

    if diff_len == 0:
        logger.warning("Empty diff — skipping review")
        return {"error": "Empty diff, nothing to review"}

    # Nothing to compute here — the orchestrator's job is to be the
    # graph's entry point and do a sanity check. Specialist agents
    # will read from state directly.
    return {}