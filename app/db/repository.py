# app/db/repository.py
import logging
from uuid import UUID
from app.db.supabase_client import get_client

logger = logging.getLogger(__name__)


def save_review(
    pr_number: int,
    repo: str,
    review_text: str,
    security_findings: dict,
    performance_findings: dict,
    architecture_findings: dict,
    model_version: str = "unknown",    # ← add this
) -> str:
    """
    Saves a completed review to the database.
    Returns the new review's UUID so it can be attached
    to the GitHub PR comment (the developer needs it to
    submit feedback).
    """
    client = get_client()

    row = {
        "pr_number":              pr_number,
        "repo":                   repo,
        "review_text":            review_text,
        "security_findings":      security_findings    or {},
        "performance_findings":   performance_findings or {},
        "architecture_findings":  architecture_findings or {},
        "model_version":          model_version,       # ← add this

    }

    response = client.table("reviews").insert(row).execute()

    review_id = response.data[0]["id"]
    logger.info(f"Review saved: {review_id} for PR #{pr_number} in {repo}")
    return review_id


def save_feedback(
    review_id: str,
    signal: str,
    comment: str = None,
) -> None:
    """
    Saves a developer's feedback on a review.
    signal must be: 'accepted', 'rejected', or 'partial'
    """
    valid_signals = {"accepted", "rejected", "partial"}
    if signal not in valid_signals:
        raise ValueError(f"signal must be one of {valid_signals}, got '{signal}'")

    client = get_client()

    row = {
        "review_id": review_id,
        "signal":    signal,
        "comment":   comment,
    }

    client.table("feedback").insert(row).execute()
    logger.info(f"Feedback saved: {signal} for review {review_id}")


def get_reviews_with_feedback(limit: int = 500) -> list[dict]:
    """
    Fetches reviews that have received feedback.
    Used in Phase 5 Chunk 2 to build fine-tuning training data.
    """
    client = get_client()

    response = (
        client.table("feedback")
        .select("signal, comment, review_id, reviews(pr_number, repo, review_text, security_findings)")
        .limit(limit)
        .execute()
    )

    logger.info(f"Fetched {len(response.data)} feedback records")
    return response.data