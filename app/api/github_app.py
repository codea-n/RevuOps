import os
import time
import logging
import httpx
import jwt  # PyJWT
from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel
from app.db.supabase_client import get_client

logger = logging.getLogger(__name__)
router = APIRouter()

def _generate_jwt() -> str:
    app_id = os.getenv("GITHUB_APP_ID")
    
    # Production: key stored as env var content
    private_key = os.getenv("GITHUB_APP_PRIVATE_KEY")
    
    # Local dev: key stored as file path
    if not private_key:
        pem_path = os.getenv("GITHUB_APP_PRIVATE_KEY_PATH")
        if not pem_path:
            raise ValueError("Either GITHUB_APP_PRIVATE_KEY or GITHUB_APP_PRIVATE_KEY_PATH must be set")
        with open(pem_path, "r") as f:
            private_key = f.read()

    if not app_id:
        raise ValueError("GITHUB_APP_ID must be set")

    now = int(time.time())
    payload = {
        "iat": now - 60,
        "exp": now + 540,
        "iss": app_id,
    }

    return jwt.encode(payload, private_key, algorithm="RS256")


async def get_installation_repos(installation_id: int) -> list[dict]:
    """
    Given an installation_id, fetch all repos GitHub App has access to.
    Uses JWT → installation token → repos list.
    Why two tokens: JWT proves app identity, installation token proves
    access to a specific installation. GitHub's security model.
    """
    jwt_token = _generate_jwt()

    async with httpx.AsyncClient() as client:
        # Step 1: exchange JWT for installation access token
        token_resp = await client.post(
            f"https://api.github.com/app/installations/{installation_id}/access_tokens",
            headers={
                "Authorization": f"Bearer {jwt_token}",
                "Accept": "application/vnd.github+json",
            }
        )
        if token_resp.status_code != 201:
            raise HTTPException(status_code=400, detail="Failed to get installation token")

        installation_token = token_resp.json()["token"]

        # Step 2: use installation token to list repos
        repos_resp = await client.get(
            "https://api.github.com/installation/repositories",
            headers={
                "Authorization": f"Bearer {installation_token}",
                "Accept": "application/vnd.github+json",
            }
        )
        if repos_resp.status_code != 200:
            raise HTTPException(status_code=400, detail="Failed to fetch repositories")

        return repos_resp.json().get("repositories", [])


class InstallRequest(BaseModel):
    installation_id: int
    user_id: str          # Supabase auth user ID
    account_login: str    # GitHub username or org name


@router.post("/github/install")
async def handle_installation(body: InstallRequest):
    """
    Called by the frontend after GitHub redirects back with installation_id.
    Stores the installation and all repos in Supabase.
    """
    supabase = get_client()

    # 1. Store the installation
    supabase.table("installations").upsert({
        "user_id": body.user_id,
        "installation_id": body.installation_id,
        "account_login": body.account_login,
    }).execute()

    # 2. Fetch repos from GitHub
    repos = await get_installation_repos(body.installation_id)

    # 3. Store each repo
    for repo in repos:
        supabase.table("repositories").upsert({
            "user_id": body.user_id,
            "installation_id": body.installation_id,
            "repo_full_name": repo["full_name"],
            "repo_id": repo["id"],
        }).execute()

    logger.info(f"Installation {body.installation_id} stored with {len(repos)} repos")
    return {"status": "ok", "repos_connected": len(repos)}


@router.get("/github/repos")
async def get_user_repos(user_id: str):
    """
    Returns all repos connected by a specific user.
    Called by the dashboard to show connected repos.
    """
    supabase = get_client()
    res = supabase.table("repositories")\
        .select("*")\
        .eq("user_id", user_id)\
        .execute()
    return {"repos": res.data}