# Shared sentence-embedding model — used by the semantic cache, the
# injection classifier and the model router.
#
# Loaded lazily on first use, not at import time: importing this module
# (which happens simply by starting the app) must not require the model
# to load successfully. PRELOAD_EMBEDDING_MODEL=true forces it via
# warmup() at startup instead of on the first /v1/chat request.
from __future__ import annotations

import numpy as np

# Classifier artifacts record the model they were trained on; scoring an
# embedding from a different model would be meaningless, so
# services/classifiers.py refuses to load a mismatched artifact.
MODEL_NAME = "all-MiniLM-L6-v2"
DIM = 384

_model = None


def _get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer(MODEL_NAME)
    return _model


def embed(text: str) -> list[float]:
    """One normalised 384-dim embedding, as a list (pgvector-ready)."""
    return _get_model().encode(text, normalize_embeddings=True).tolist()


def embed_many(texts: list[str]) -> np.ndarray:
    """Normalised embeddings for several texts in one batch, shape (n, 384)."""
    if not texts:
        return np.zeros((0, DIM), dtype=np.float32)
    return np.asarray(_get_model().encode(texts, normalize_embeddings=True), dtype=np.float32)


def warmup() -> bool:
    """Force the embedding model to load now instead of on first use."""
    try:
        _get_model().encode("warmup", normalize_embeddings=True)
        return True
    except Exception:
        return False
