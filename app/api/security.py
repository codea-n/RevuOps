# app/api/security.py
import os
import logging
from fastapi import Request, HTTPException
from slowapi import Limiter
from slowapi.util import get_remote_address

logger = logging.getLogger(__name__)

# Rate limiter — keyed by IP address
# get_remote_address extracts the caller's IP from the request
limiter = Limiter(key_func=get_remote_address)

FEEDBACK_SECRET = os.getenv("AUTOREVIEW_FEEDBACK_SECRET", "")


def verify_feedback_secret(request: Request) -> None:
    """
    Checks that the request includes the correct secret header.
    Raises 401 if missing or wrong.

    Callers must include:
        X-AutoReview-Secret: your_secret_here
    """
    if not FEEDBACK_SECRET:
        # If no secret is configured, warn but allow through.
        # This prevents locking yourself out during local development
        # before the env var is set.
        logger.warning("AUTOREVIEW_FEEDBACK_SECRET not set — skipping auth check")
        return

    incoming = request.headers.get("X-AutoReview-Secret", "")

    # hmac.compare_digest prevents timing attacks.
    # A regular == comparison leaks information about how many
    # characters matched before the mismatch — an attacker can
    # use timing differences to guess the secret character by character.
    # compare_digest always takes the same time regardless of where
    # the strings differ.
    import hmac
    if not hmac.compare_digest(incoming, FEEDBACK_SECRET):
        logger.warning(f"Invalid feedback secret from {get_remote_address(request)}")
        raise HTTPException(status_code=401, detail="Invalid secret")