# app/agents/architecture_agent.py
import logging
from app.agents.state import ReviewState
from app.tools.ast_parser import run as ast_run
from app.agents.diff_utils import extract_code_from_diff

logger = logging.getLogger(__name__)



def architecture_node(state: ReviewState) -> dict:
    """
    Analyses code structure and enriches findings with RAG context.
    Flags: missing imports, deeply nested classes, and structural
    patterns that match known anti-patterns in the vector store.
    """
    diff        = state.get("diff", "")
    rag_context = state.get("rag_context", "")

    if not diff:
        return {"architecture_findings": {"notes": [], "skipped": True}}

    logger.info("Architecture agent: running AST + RAG enrichment")
    code = extract_code_from_diff(diff)   # ← ADD
    ast_result = ast_run(code)            # ← change diff to code
    notes = []

    # --- Structural checks ---
    imports   = ast_result.get("imports", [])
    classes   = ast_result.get("classes", [])
    functions = ast_result.get("functions", [])

    if not imports and functions:
        notes.append({
            "type":    "missing_imports",
            "message": "Functions present but no imports detected. "
                       "Diff may be incomplete or missing dependencies.",
        })

    for cls in classes:
        method_count = len(cls.get("methods", []))
        if method_count > 15:
            notes.append({
                "type":    "large_class",
                "class":   cls.get("name"),
                "methods": method_count,
                "message": f"Class '{cls.get('name')}' has {method_count} methods. "
                           "Consider splitting (Single Responsibility Principle).",
            })

    # --- RAG enrichment ---
    # If Pinecone returned similar code, attach it as context for the
    # Supervisor. The Supervisor prompt will use this to say things like
    # "similar code in your codebase already does X — consider reusing it."
    rag_note = None
    if rag_context and rag_context.strip():
        rag_note = {
            "type":    "similar_code_found",
            "message": "Similar code patterns found in the codebase.",
            "context": rag_context[:800],  # trim to avoid bloating the prompt
        }
        notes.append(rag_note)
        logger.info("Architecture agent: RAG context attached")
    else:
        logger.info("Architecture agent: no RAG context available")

    return {
        "architecture_findings": {
            "notes":       notes,
            "class_count": len(classes),
            "func_count":  len(functions),
            "has_rag":     rag_note is not None,
            "skipped":     False,
        }
    }