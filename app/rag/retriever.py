from pinecone import Pinecone
from typing import List, Dict, Any
import os
import hashlib

from app.rag.embedder import embed_texts, embed_single
from app.rag.chunker import CodeChunk


def _get_client() -> Pinecone:
    """Initialize Pinecone client from environment."""
    api_key = os.getenv("PINECONE_API_KEY")
    if not api_key:
        raise ValueError("PINECONE_API_KEY not set in environment")
    return Pinecone(api_key=api_key)


def _get_index():
    """Get the Pinecone index object."""
    pc = _get_client()
    index_name = os.getenv("PINECONE_INDEX_NAME", "auto-reviewer")
    return pc.Index(index_name)


def upsert_chunks(chunks: List[CodeChunk]) -> int:
    """
    Embed a list of CodeChunks and upsert them into Pinecone.

    Returns the number of vectors upserted.

    Why upsert and not insert? Pinecone's upsert is idempotent —
    if a vector with the same ID already exists, it's overwritten.
    This means re-processing a PR won't create duplicates.
    """
    if not chunks:
        return 0

    index = _get_index()
    texts = [c.content for c in chunks]
    embeddings = embed_texts(texts)

    vectors = []
    for chunk, embedding in zip(chunks, embeddings):
        # Deterministic ID: same chunk always gets same ID → safe to re-upsert
        vector_id = _make_vector_id(chunk)
        vectors.append({
            "id": vector_id,
            "values": embedding,
            "metadata": {
                "content": chunk.content[:1000],  # Pinecone metadata cap is 40KB; be conservative
                "pr_number": chunk.pr_number,
                "repo": chunk.repo,
                "file_hint": chunk.file_hint,
                "chunk_index": chunk.chunk_index,
            }
        })

    # Pinecone recommends batches of 100 max
    batch_size = 100
    for i in range(0, len(vectors), batch_size):
        batch = vectors[i:i + batch_size]
        index.upsert(vectors=batch)

    return len(vectors)


def query_similar(
    query_text: str,
    top_k: int = 5,
    filter_repo: str | None = None,
) -> List[Dict[str, Any]]:
    """
    Find the top-k most similar code chunks to a query string.

    Returns a list of metadata dicts for the matched chunks.

    Args:
        query_text: The code or description to find similar chunks for.
        top_k: Number of results to return.
        filter_repo: Optional — restrict results to a specific repo.
    """
    index = _get_index()
    query_embedding = embed_single(query_text)

    query_kwargs: Dict[str, Any] = {
        "vector": query_embedding,
        "top_k": top_k,
        "include_metadata": True,
    }

    if filter_repo:
        query_kwargs["filter"] = {"repo": {"$eq": filter_repo}}

    results = index.query(**query_kwargs)

    return [
        {
            "score": match["score"],
            "content": match["metadata"].get("content", ""),
            "pr_number": match["metadata"].get("pr_number"),
            "repo": match["metadata"].get("repo"),
            "file_hint": match["metadata"].get("file_hint"),
        }
        for match in results["matches"]
    ]


def _make_vector_id(chunk: CodeChunk) -> str:
    """
    Generate a deterministic, unique ID for a chunk.

    Format: sha256(repo + pr_number + chunk_index)[:16]
    Short enough to be readable, long enough to avoid collisions.
    """
    raw = f"{chunk.repo}:{chunk.pr_number}:{chunk.chunk_index}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]