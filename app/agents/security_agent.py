# app/agents/security_agent.py
# from app.tools.ruff_linter import RuffLinter
# from app.tools.bandit_scanner import BanditScanner
# ruff = RuffLinter()
# bandit = BanditScanner()
import logging
from app.agents.state import ReviewState
from app.agents.diff_utils import extract_code_from_diff

# ADD these 2 lines:
from app.tools.ruff_linter import run as ruff_run
from app.tools.bandit_scanner import run as bandit_run

logger = logging.getLogger(__name__)



def security_node(state: ReviewState) -> dict:
    diff = state.get("diff", "")
    if not diff:
        return {"security_findings": {"issues": [], "high_count": 0, "skipped": True}}

    logger.info("Security agent: running Ruff + Bandit")
    code = extract_code_from_diff(diff)   # ← ADD THIS

    ruff_result   = ruff_run(code)        # ← change diff to code
    bandit_result = bandit_run(code)      # ← change diff to code



    # Ruff returns all issues including S* (security) rules.
    # Filter to only the S-prefixed ones — style issues belong
    # to Architecture, not Security.
    # The ruff_security filter reads "code" but your tool returns "rule_code"
    # TO:
    ruff_security = [
        issue for issue in ruff_result.get("issues", [])
        if (issue.get("code") or issue.get("rule_code") or "").startswith("S")
    ]

    # And the dedup key also reads "code" — fix that too:
  
    # TO:
    # key = (issue.get("line"), (issue.get("code") or issue.get("rule_code") or "")[1:])

    # Deduplicate: Ruff S608 and Bandit B608 are the same finding.
    # Key on (line_number, rule_code_suffix) to collapse duplicates.
    seen = set()
    deduped = []

    for item in ruff_security:
        key = (item.get("line"), (item.get("code") or item.get("rule_code") or "")[1:])
        if key not in seen:
            seen.add(key)
            deduped.append({**item, "source": "ruff"})

    for item in bandit_result.get("issues", []):
        key = (item.get("line"), str(item.get("test_id", ""))[1:])
        if key not in seen:
            seen.add(key)
            deduped.append({**item, "source": "bandit"})



    high_count = sum(
        1 for i in deduped
        if i.get("severity", "").upper() == "HIGH"
        or i.get("confidence", "").upper() == "HIGH"
    )

    logger.info(f"Security agent: {len(deduped)} unique findings, {high_count} high severity")

    return {
        "security_findings": {
            "issues":     deduped,
            "high_count": high_count,
            "skipped":    False,
        }
    }