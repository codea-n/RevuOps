# test_graph.py  — run once, then delete
import asyncio, os
from dotenv import load_dotenv
load_dotenv()

from app.agents.graph import review_graph

SAMPLE_DIFF = """
--- a/app/utils.py
+++ b/app/utils.py
@@ -0,0 +1,5 @@
+def get_user(user_id):
+    import hashlib
+    token = hashlib.md5(user_id.encode()).hexdigest()
+    query = f"SELECT * FROM users WHERE id = {user_id}"
+    return query, token
"""

async def main():
    state = {
        "pr_number": 42,
        "repo_full_name": "test/repo",
        "diff": SAMPLE_DIFF,
        "rag_context": "",
        "security_findings": None,
        "performance_findings": None,
        "architecture_findings": None,
        "final_review": None,
        "error": None,
    }
    result = await review_graph.ainvoke(state)
    print("\n=== FINAL REVIEW ===")
    print(result["final_review"])
    print("\n=== SECURITY FINDINGS ===")
    print(result["security_findings"])

asyncio.run(main())