from fastapi import APIRouter, Request, HTTPException, Header
import hmac
import hashlib
import os
# At the top of webhook.py, add this import:
from app.agents.graph import review_graph
from app.db.repository import save_review


router = APIRouter()

@router.post("/webhook/github")
async def github_webhook(
    request: Request,
    x_hub_signature_256: str = Header(None),
    x_github_event: str = Header(None)
):
    payload = await request.body()

    # Verify the request came from GitHub
    _verify_signature(payload, x_hub_signature_256)

    body = await request.json()
    action = body.get("action")

    if x_github_event == "pull_request" and action in ("opened", "synchronize"):
        pr = body["pull_request"]
        pr_info = {
            "pr_number": pr["number"],
            "title": pr["title"],
            "author": pr["user"]["login"],
            "repo": body["repository"]["full_name"],
            "base_branch": pr["base"]["ref"],
            "head_branch": pr["head"]["ref"],
            "diff_url": pr["diff_url"],
        }
        initial_state = {
        "pr_number":      pr_info["pr_number"],
        "repo_full_name": pr_info["repo_full_name"],
        "diff":           pr_info.get("diff", ""),
        "rag_context":    pr_info.get("rag_context", ""),
        # Specialist outputs start as None
        "security_findings":     None,
        "performance_findings":  None,
        "architecture_findings": None,
        "final_review":          None,
        "model_version":         None,
        "error":                 None,
        }

        result = await review_graph.ainvoke(initial_state)
        review_id = save_review(
        pr_number            = pr_info["pr_number"],
        repo                 = pr_info["repo_full_name"],
        review_text          = result.get("final_review", ""),
        security_findings    = result.get("security_findings"),
        performance_findings = result.get("performance_findings"),
        architecture_findings= result.get("architecture_findings"),
        model_version=result.get("model_version", "unknown"),  # ← add this
        )
        logger.info(f"Review {review_id} saved to Supabase")
        comment_body = result.get("final_review", "") + f"\n\n<!-- autoreview_id:{review_id} -->"
        final_review = result.get("final_review", "")
        logger.info(f"Review complete for PR #{pr_info['pr_number']}")
        print(f"[AutoReviewer] PR received: {pr_info}")
        return {"status": "queued", "pr": pr_info}

    # All other events acknowledged but ignored for now
    return {"status": "ignored", "event": x_github_event, "action": action}


def _verify_signature(payload: bytes, signature_header: str):
    secret = os.getenv("GITHUB_WEBHOOK_SECRET")
    if not secret:
        raise HTTPException(status_code=500, detail="Webhook secret not configured")
    if not signature_header:
        raise HTTPException(status_code=401, detail="Missing signature header")

    expected = "sha256=" + hmac.new(
        secret.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(expected, signature_header):
        raise HTTPException(status_code=401, detail="Invalid signature")