# Loads and scores the classifiers trained in ml/ — the prompt-injection
# detector and the easy/hard model router.
#
# Artifacts are plain JSON (backend/app/artifacts/*.json): weights, bias,
# threshold and, for text components, a TF-IDF vocabulary + idf vector.
# Not pickle — unpickling executes whatever the file contains — and not
# a fitted sklearn object, so an sklearn upgrade can't silently change
# what a saved model means. ml/common.py writes this format and
# ml/train_*.py verify after export that scores computed here match
# training-time scores exactly.
#
# A classifier is an ensemble of linear components whose logits are
# averaged:
#   embedding_logreg  — logistic regression over the shared sentence
#                       embedding (services/embeddings.py)
#   tfidf_logreg      — logistic regression over a TF-IDF vector rebuilt
#                       from the stored vocabulary and idf
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np

from app.services.embeddings import MODEL_NAME

logger = logging.getLogger(__name__)

ARTIFACT_DIR = Path(__file__).resolve().parent.parent / "artifacts"


def sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-x))


def _tfidf_from_spec(spec: dict):
    from sklearn.feature_extraction.text import TfidfVectorizer

    vec = TfidfVectorizer(
        analyzer=spec["analyzer"],
        ngram_range=tuple(spec["ngram_range"]),
        lowercase=spec["lowercase"],
        sublinear_tf=spec["sublinear_tf"],
        token_pattern=spec.get("token_pattern", r"(?u)\b\w\w+\b"),
        vocabulary={term: i for i, term in enumerate(spec["vocabulary"])},
        dtype=np.float64,
    )
    vec.idf_ = np.asarray(spec["idf"], dtype=np.float64)
    return vec


@dataclass
class _Component:
    kind: str
    weights: np.ndarray
    bias: float
    vectorizer: object | None = None

    def logits(self, texts: list[str], embeddings: np.ndarray) -> np.ndarray:
        if self.kind == "embedding_logreg":
            return embeddings @ self.weights + self.bias
        features = self.vectorizer.transform(texts)
        return np.asarray(features @ self.weights).ravel() + self.bias


class EnsembleClassifier:
    """Averages component logits; `threshold` is in logit space."""

    def __init__(self, artifact: dict) -> None:
        if artifact["embedding_model"] != MODEL_NAME:
            raise ValueError(
                f"{artifact['name']} was trained on {artifact['embedding_model']!r} "
                f"but the gateway embeds with {MODEL_NAME!r}"
            )
        self.name: str = artifact["name"]
        self.threshold: float = float(artifact["threshold"])
        self.meta = {k: v for k, v in artifact.items() if k not in ("components",)}
        self.components = [
            _Component(
                kind=c["type"],
                weights=np.asarray(c["weights"], dtype=np.float64),
                bias=float(c["bias"]),
                vectorizer=_tfidf_from_spec(c["vectorizer"]) if c["type"] == "tfidf_logreg" else None,
            )
            for c in artifact["components"]
        ]

    def logits(self, texts: list[str], embeddings: np.ndarray) -> np.ndarray:
        if not texts:
            return np.zeros(0)
        stacked = [c.logits(texts, embeddings) for c in self.components]
        return np.mean(stacked, axis=0)

    def probabilities(self, texts: list[str], embeddings: np.ndarray) -> np.ndarray:
        return sigmoid(self.logits(texts, embeddings))

    @property
    def probability_threshold(self) -> float:
        return float(sigmoid(np.array(self.threshold)))


def load_artifact(name: str, directory: Path = ARTIFACT_DIR) -> EnsembleClassifier | None:
    """
    Load one classifier, or None if its artifact is missing or unreadable.
    A missing classifier disables that feature with a logged warning — it
    never stops the gateway from serving.
    """
    path = directory / f"{name}.json"
    try:
        return EnsembleClassifier(json.loads(path.read_text()))
    except FileNotFoundError:
        logger.warning("classifier artifact %s not found — feature disabled", path)
    except Exception as e:
        logger.error("failed to load classifier artifact %s — feature disabled: %s", path, e)
    return None


@lru_cache(maxsize=None)
def get(name: str) -> EnsembleClassifier | None:
    return load_artifact(name)
