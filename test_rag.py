# test_rag.py  ← delete this after confirming it works
import os
from dotenv import load_dotenv
load_dotenv()

from app.rag.chunker import chunk_diff
from app.rag.retriever import upsert_chunks, query_similar

SAMPLE_DIFF = """diff --git a/auth.py b/auth.py
index 1234567..abcdefg 100644
--- a/auth.py
+++ b/auth.py
@@ -10,6 +10,12 @@ class AuthService:
     def login(self, username: str, password: str):
+        # WARNING: storing plaintext password
+        self.db.execute(
+            f"SELECT * FROM users WHERE password = '{password}'"
+        )
         return self.db.query(username)
diff --git a/utils.py b/utils.py
index 0000001..9999999 100644
--- a/utils.py
+++ b/utils.py
@@ -1,5 +1,8 @@
+def process_data(items):
+    result = []
+    for i in range(len(items)):
+        result.append(items[i] * 2)
+    return result
"""

print("=== Step 1: Chunking diff ===")
chunks = chunk_diff(SAMPLE_DIFF, pr_number=42, repo="testuser/test-repo")
print(f"Created {len(chunks)} chunks:")
for c in chunks:
    print(f"  [{c.chunk_index}] {c.file_hint}: {c.content[:60].strip()!r}...")

print("\n=== Step 2: Upserting to Pinecone ===")
count = upsert_chunks(chunks)
print(f"Upserted {count} vectors")

print("\n=== Step 3: Querying ===")
results = query_similar("SQL injection vulnerability password plaintext", top_k=3)
print(f"Top {len(results)} results:")
for r in results:
    print(f"  score={r['score']:.3f} | file={r['file_hint']} | {r['content'][:80].strip()!r}")

print("RAG pipeline working end-to-end")