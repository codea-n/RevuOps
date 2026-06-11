from sentence_transformers import SentenceTransformer
from typing import List
import numpy as np

# Module-level singleton — load the model once, reuse it.
# Loading on every call would cost ~2s each time. This way
# it loads once when the module is first imported.
_model: SentenceTransformer | None = None

MODEL_NAME = "all-MiniLM-L6-v2"


def get_model() -> SentenceTransformer:
    """Lazy-load the embedding model (singleton pattern)."""
    global _model
    if _model is None:
        print(f"[Embedder] Loading model: {MODEL_NAME}")
        _model = SentenceTransformer(MODEL_NAME)
        print("[Embedder] Model loaded.")
    return _model


def embed_texts(texts: List[str]) -> List[List[float]]:
    """
    Convert a list of text strings into embedding vectors.

    Returns a list of float lists (Pinecone expects plain Python floats,
    not numpy types — we convert explicitly).
    """
    model = get_model()
    embeddings: np.ndarray = model.encode(texts, show_progress_bar=False)
    return embeddings.tolist()


def embed_single(text: str) -> List[float]:
    """Convenience wrapper for embedding one string."""
    return embed_texts([text])[0]