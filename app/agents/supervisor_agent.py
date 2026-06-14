# app/agents/supervisor_agent.py
import logging
import os
from groq import Groq
from app.agents.state import ReviewState

logger = logging.getLogger(__name__)
client = Groq(api_key=os.getenv("GROQ_API_KEY"))
MODEL_VERSION = "llama-3.3-70b-versatile"

SYSTEM_PROMPT = """You are an expert code reviewer. You receive structured findings 
from three analysis tools and write a concise, actionable GitHub PR comment.

Rules:
- Be specific: reference line numbers and function names when available
- Be constructive: suggest fixes, not just problems  
- Prioritise: lead with HIGH severity security issues if any exist
- Be brief: a developer will read this in 60 seconds
- Format: use markdown with ## headers for each section
- Skip sections with no findings — don't write "No issues found" for every tool
- End with a one-line summary verdict: APPROVE / REQUEST_CHANGES / COMMENT
- Rules for verdict: any HIGH severity issue = REQUEST_CHANGES, any MEDIUM = COMMENT, all low/warning = APPROVE"""


def _build_prompt(state: ReviewState) -> str:
    sec  = state.get("security_findings")    or {}
    perf = state.get("performance_findings") or {}
    arch = state.get("architecture_findings") or {}

    parts = ["## Findings to review\n"]

    # Security
    issues = sec.get("issues", [])
    if issues:
        parts.append("### Security")
        for i in issues:
            line = i.get('line', '?')
            code = i.get('code') or i.get('test_id', '?')
            msg  = i.get('message') or i.get('issue_text', '')
            sev  = i.get('severity', '').upper()
            src  = i.get('source', '')
            parts.append(f"- Line {line} [{code}] {msg} (severity: {sev}, tool: {src})")

    # Performance
    hotspots = perf.get("hotspots", [])
    if hotspots:
        parts.append("\n### Performance")
        for h in hotspots:
            fn  = h.get('function', '?')
            ln  = h.get('line', '?')
            for issue in h.get('issues', []):
                parts.append(f"- `{fn}` at line {ln}: {issue}")

    # Architecture
    notes = arch.get("notes", [])
    if notes:
        parts.append("\n### Architecture")
        for n in notes:
            if n.get("type") == "similar_code_found":
                parts.append(f"- Similar patterns found in codebase:\n```\n{n.get('context','')}\n```")
            else:
                parts.append(f"- {n.get('message', '')}")

    if len(parts) == 1:
        # No findings at all
        parts.append("All checks passed — no issues found.")

    return "\n".join(parts)


def supervisor_node(state: ReviewState) -> dict:
    """
    Builds a prompt from all specialist findings and calls Groq
    to produce a structured markdown PR review comment.
    """
    logger.info("Supervisor: building prompt from findings")
    user_prompt = _build_prompt(state)

    logger.info("Supervisor: calling Groq (Llama 3.3 70B)")
    try:
        response = client.chat.completions.create(
            model=MODEL_VERSION,   # ← was hardcoded string before
            messages=[...],
            temperature=0.2,
            max_tokens=1024,
        )

        review = response.choices[0].message.content
        logger.info("Supervisor: review generated successfully")
    except Exception as e:
        logger.error(f"Supervisor: Groq call failed — {e}")
        review = f"⚠️ AutoReviewer error: could not generate review ({e})"

    return {
    "final_review": review,
    "model_version": MODEL_VERSION,   # ← add this
    }
