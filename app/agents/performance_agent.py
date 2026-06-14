# app/agents/performance_agent.py
import logging
from app.agents.state import ReviewState
from app.agents.diff_utils import extract_code_from_diff

logger = logging.getLogger(__name__)

from app.tools.ast_parser import run as ast_run

COMPLEXITY_THRESHOLD = 10   # same threshold as Phase 3
LOC_THRESHOLD        = 50   # functions longer than this are flagged


def performance_node(state: ReviewState) -> dict:
    """
    Runs AST analysis on the diff to find complexity and size hotspots.
    """
    diff = state.get("diff", "")
    if not diff:
        return {"performance_findings": {"hotspots": [], "skipped": True}}

    logger.info("Performance agent: running AST parser")
    code = extract_code_from_diff(diff)
    ast_result = ast_run(code)


    functions  = ast_result.get("functions", [])
    hotspots   = []

    for fn in functions:
        issues = []
        complexity = fn.get("complexity", 1)
        loc        = fn.get("loc", 0)

        if complexity >= COMPLEXITY_THRESHOLD:
            issues.append(
                f"High cyclomatic complexity: {complexity} "
                f"(threshold: {COMPLEXITY_THRESHOLD})"
            )

        if loc >= LOC_THRESHOLD:
            issues.append(
                f"Long function: {loc} lines "
                f"(threshold: {LOC_THRESHOLD})"
            )

        if issues:
            hotspots.append({
                "function":   fn.get("name"),
                "line":       fn.get("line"),
                "complexity": complexity,
                "loc":        loc,
                "issues":     issues,
            })

    logger.info(f"Performance agent: {len(hotspots)} hotspots found")

    return {
        "performance_findings": {
            "hotspots":   hotspots,
            "total_functions": len(functions),
            "skipped":    False,
        }
    }