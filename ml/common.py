"""
Shared helpers for the training scripts: dataset download, cached
embedding, evaluation and artifact export.

Both classifiers are logistic regressions over the same sentence
embeddings the gateway already computes for its semantic cache
(all-MiniLM-L6-v2, 384 dims, L2-normalised). Reusing that model means
classification adds no second model to load and almost no latency at
serve time — the expensive part, the embedding, is shared.
"""
from __future__ import annotations

import hashlib
import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import precision_recall_fscore_support, roc_auc_score

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / ".data"
REPORT_DIR = ROOT / "reports"
ARTIFACT_DIR = ROOT.parent / "backend" / "app" / "artifacts"

# Must match the model in backend/app/services/embeddings.py — a
# classifier trained on one embedding space is meaningless in another.
EMBED_MODEL = "all-MiniLM-L6-v2"
SEED = 42

_HF_PARQUET = "https://huggingface.co/api/datasets/{repo}/parquet/default/{split}/0.parquet"


def fetch(repo: str, split: str) -> pd.DataFrame:
    """Download one split of a Hugging Face dataset as parquet (cached on disk)."""
    DATA_DIR.mkdir(exist_ok=True)
    path = DATA_DIR / f"{repo.replace('/', '__')}__{split}.parquet"
    if not path.exists():
        print(f"  downloading {repo} [{split}]")
        urllib.request.urlretrieve(_HF_PARQUET.format(repo=repo, split=split), path)
    return pd.read_parquet(path)


def normalise(text: str) -> str:
    return " ".join(str(text).split())


def embed(texts: list[str], cache_name: str) -> np.ndarray:
    """
    Embed texts with the gateway's embedding model, caching the result on
    disk keyed by a hash of the exact input list — re-running a script
    with unchanged data skips the slow part.
    """
    digest = hashlib.sha1("\x00".join(texts).encode()).hexdigest()[:16]
    path = DATA_DIR / f"emb__{cache_name}__{digest}.npy"
    if path.exists():
        return np.load(path)

    from sentence_transformers import SentenceTransformer

    print(f"  embedding {len(texts):,} texts ({cache_name}) …")
    model = SentenceTransformer(EMBED_MODEL, device="cpu")
    vecs = model.encode(texts, batch_size=64, normalize_embeddings=True, show_progress_bar=True)
    vecs = np.asarray(vecs, dtype=np.float32)
    DATA_DIR.mkdir(exist_ok=True)
    np.save(path, vecs)
    return vecs


def binary_report(y_true: np.ndarray, scores: np.ndarray, threshold: float) -> dict:
    """Metrics at a fixed decision threshold, plus threshold-free ROC-AUC."""
    y_pred = (scores >= threshold).astype(int)
    p, r, f1, _ = precision_recall_fscore_support(y_true, y_pred, average="binary", zero_division=0)
    negatives = y_true == 0
    fpr = float(y_pred[negatives].mean()) if negatives.any() else 0.0
    return {
        "n": int(len(y_true)),
        "positives": int(y_true.sum()),
        "roc_auc": round(float(roc_auc_score(y_true, scores)), 4) if len(set(y_true)) > 1 else None,
        "precision": round(float(p), 4),
        "recall": round(float(r), 4),
        "f1": round(float(f1), 4),
        "false_positive_rate": round(fpr, 4),
    }


def embedding_component(clf) -> dict:
    """A logistic regression over the shared sentence embedding."""
    return {
        "type": "embedding_logreg",
        "weights": [round(float(w), 6) for w in clf.coef_[0]],
        "bias": round(float(clf.intercept_[0]), 6),
    }


def tfidf_component(vec, clf) -> dict:
    """A logistic regression over a TF-IDF vector, with the vocabulary and idf needed to rebuild it."""
    vocab = sorted(vec.vocabulary_, key=vec.vocabulary_.__getitem__)
    return {
        "type": "tfidf_logreg",
        "vectorizer": {
            "analyzer": vec.analyzer,
            "ngram_range": list(vec.ngram_range),
            "lowercase": vec.lowercase,
            "sublinear_tf": vec.sublinear_tf,
            "token_pattern": vec.token_pattern,
            "vocabulary": vocab,
            "idf": [round(float(v), 6) for v in vec.idf_],
        },
        "weights": [round(float(w), 6) for w in np.asarray(clf.coef_[0]).ravel()],
        "bias": round(float(clf.intercept_[0]), 6),
    }


def export_ensemble(name: str, components: list[dict], threshold_logit: float, meta: dict) -> Path:
    """
    Write an ensemble of linear components as plain JSON. The gateway
    averages the components' logits and compares against the threshold
    (backend/app/services/classifiers.py) — no scikit-learn model object
    and no pickle, which would execute whatever is in the file at load time.
    """
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    artifact = {
        "name": name,
        "embedding_model": EMBED_MODEL,
        "threshold": round(float(threshold_logit), 6),
        "threshold_space": "mean component logit",
        "trained_at": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        **meta,
        "components": components,
    }
    path = ARTIFACT_DIR / f"{name}.json"
    path.write_text(json.dumps(artifact, separators=(",", ":")) + "\n")
    return path


def verify_artifact(name: str, texts: list[str], embeddings: np.ndarray, expected_logits: np.ndarray) -> float:
    """
    Load the exported artifact the way the gateway does and check it
    reproduces the training-time scores. Guards against the serving code
    and the export format drifting apart.
    """
    import sys

    sys.path.insert(0, str(ROOT.parent / "backend"))
    from app.services.classifiers import load_artifact

    clf = load_artifact(name, ARTIFACT_DIR)
    if clf is None:
        raise RuntimeError(f"gateway could not load {name}")
    served = clf.logits(texts, embeddings)
    max_diff = float(np.max(np.abs(served - expected_logits)))
    if max_diff > 1e-3:
        raise RuntimeError(f"{name}: served logits differ from training by up to {max_diff:.2e}")
    return max_diff


def write_report(name: str, report: dict) -> Path:
    REPORT_DIR.mkdir(exist_ok=True)
    path = REPORT_DIR / f"{name}.json"
    path.write_text(json.dumps(report, indent=2) + "\n")
    return path
