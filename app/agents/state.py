# app/agents/state.py
from typing import TypedDict, Optional


class ReviewState(TypedDict):
    # --- INPUT (set by Orchestrator, read-only for all agents) ---
    pr_number: int
    repo_full_name: str        # e.g. "alice/my-project"
    diff: str                  # raw unified diff text
    rag_context: str           # similar code retrieved from Pinecone

    # --- SPECIALIST AGENT OUTPUTS (each agent writes its own key) ---
    security_findings: Optional[dict]
    performance_findings: Optional[dict]
    architecture_findings: Optional[dict]

    # --- SUPERVISOR OUTPUT ---
    final_review: Optional[str]  # the markdown comment to post to GitHub
    model_version: Optional[str]    # ← add this


    # --- METADATA (for LangSmith tracing) ---
    error: Optional[str]         # any agent can write here if it fails