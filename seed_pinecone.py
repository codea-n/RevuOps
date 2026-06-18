"""
seed_pinecone.py — index the auto-reviewer codebase into Pinecone.

Run once locally to populate the vector DB so the architecture agent
has real context to retrieve from.

Usage:
    python seed_pinecone.py
"""
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

from app.rag.chunker import CodeChunk, chunk_diff
from app.rag.retriever import upsert_chunks

REPO = "auto-reviewer/auto-reviewer"
EXTENSIONS = {".py"}
SKIP_DIRS = {"venv", "__pycache__", ".git", ".github", "node_modules"}


def read_file_as_fake_diff(filepath: Path, repo_root: Path) -> str:
    """
    Wrap a source file in a minimal diff format so the chunker
    can parse it. We don't have real git diffs for local files,
    so we fake the header.
    """
    relative = filepath.relative_to(repo_root)
    content = filepath.read_text(encoding="utf-8", errors="ignore")
    lines = "\n".join(f"+{line}" for line in content.splitlines())
    return f"diff --git a/{relative} b/{relative}\n@@ -0,0 +1 @@\n{lines}"


def collect_python_files(root: Path):
    for path in root.rglob("*"):
        if path.suffix not in EXTENSIONS:
            continue
        if any(skip in path.parts for skip in SKIP_DIRS):
            continue
        yield path


def main():
    repo_root = Path(__file__).parent
    files = list(collect_python_files(repo_root))
    print(f"Found {len(files)} Python files to index")

    all_chunks = []
    for i, filepath in enumerate(files):
        fake_diff = read_file_as_fake_diff(filepath, repo_root)
        chunks = chunk_diff(
            diff_text=fake_diff,
            pr_number=0,
            repo=REPO,
        )
        all_chunks.extend(chunks)
        print(f"  [{i+1}/{len(files)}] {filepath.name} → {len(chunks)} chunks")

    print(f"\nTotal chunks: {len(all_chunks)}")
    print("Upserting to Pinecone...")
    count = upsert_chunks(all_chunks)
    print(f"Done — {count} vectors upserted.")


if __name__ == "__main__":
    main()