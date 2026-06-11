# app/api/feedback.py
import logging
from fastapi import APIRouter, HTTPException, Request
from slowapi.errors import RateLimitExceeded
from pydantic import BaseModel
from app.db.repository import save_feedback
from app.api.security import limiter, verify_feedback_secret

logger = logging.getLogger(__name__)
router = APIRouter()


class FeedbackRequest(BaseModel):
    review_id: str
    signal: str
    comment: str = None


@router.post("/feedback")
@limiter.limit("10/minute")   # max 10 requests per IP per minute
async def receive_feedback(request: Request, body: FeedbackRequest):
    """
    Receives developer feedback on a review.
    Protected by shared secret + rate limiting.
    """
    # Auth check first — fail fast before any db work
    verify_feedback_secret(request)

    valid_signals = {"accepted", "rejected", "partial"}
    if body.signal not in valid_signals:
        raise HTTPException(
            status_code=400,
            detail=f"signal must be one of {valid_signals}"
        )

    try:
        save_feedback(
            review_id=body.review_id,
            signal=body.signal,
            comment=body.comment,
        )
        logger.info(f"Feedback received: {body.signal} for review {body.review_id}")
        return {"status": "ok", "review_id": body.review_id}

    except Exception as e:
        logger.error(f"Failed to save feedback: {e}")
        raise HTTPException(status_code=500, detail=str(e))