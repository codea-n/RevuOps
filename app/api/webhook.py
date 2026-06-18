import hmac
import hashlib
import logging
import os

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request

from app.agents.graph import review_graph
from app.api.github_client import post_pr_comment
from app.db.repository import save_review

router = APIRouter()
logger = logging.getLogger(__name__)


async def _run_review(pr_info: dict):
    try:
        initial_state = {
            "pr_number":              pr_info["pr_number"],
            "repo_full_name":         pr_info["repo"],
            "diff":                   pr_info.get("diff", ""),
            "rag_context":            pr_info.get("rag_context", ""),
            "security_findings":      None,
            "performance_findings":   None,
            "architecture_findings":  None,
            "final_review":           None,
            "model_version":          None,
            "error":                  None,
        }

        result = await review_graph.ainvoke(initial_state)

        review_id = save_review(
            pr_number             = pr_info["pr_number"],
            repo                  = pr_info["repo"],
            review_text           = result.get("final_review", ""),
            security_findings     = result.get("security_findings"),
            performance_findings  = result.get("performance_findings"),
            architecture_findings = result.get("architecture_findings"),
            model_version         = result.get("model_version", "unknown"),
        )

        comment_body = result.get("final_review", "") + f"\n\n<!-- autoreview_id:{review_id} -->"

        await post_pr_comment(
            repo_full_name = pr_info["repo"],
            pr_number      = pr_info["pr_number"],
            body           = comment_body,
        )

        logger.info(f"Review {review_id} posted to PR #{pr_info['pr_number']}")

    except Exception as e:
        logger.error(f"Review failed for PR #{pr_info['pr_number']}: {e}")


@router.post("/webhook/github")
async def github_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_hub_signature_256: str = Header(None),
    x_github_event: str = Header(None),
):
    payload = await request.body()
    _verify_signature(payload, x_hub_signature_256)

    import json
    body = json.loads(payload)

    action = body.get("action")

    if x_github_event == "pull_request" and action in ("opened", "synchronize"):
        pr = body["pull_request"]
        pr_info = {
            "pr_number":   pr["number"],
            "title":       pr["title"],
            "author":      pr["user"]["login"],
            "repo":        body["repository"]["full_name"],
            "base_branch": pr["base"]["ref"],
            "head_branch": pr["head"]["ref"],
            "diff_url":    pr["diff_url"],
        }

        background_tasks.add_task(_run_review, pr_info)
        return {"status": "queued", "pr": pr_info}

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