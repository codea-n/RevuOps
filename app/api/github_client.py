import httpx
import os

GITHUB_API = "https://api.github.com"


async def post_pr_comment(repo_full_name: str, pr_number: int, body: str) -> bool:
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        raise ValueError("GITHUB_TOKEN not configured")

    url = f"{GITHUB_API}/repos/{repo_full_name}/issues/{pr_number}/comments"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(url, json={"body": body}, headers=headers)
        response.raise_for_status()
        return True