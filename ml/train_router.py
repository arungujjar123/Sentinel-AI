"""
Train the easy/hard model router.

    python ml/train_router.py

Data: routellm/gpt4_dataset (Apache-2.0), from LMSYS's RouteLLM work.
Each prompt was answered by Mixtral-8x7B and the answer graded 1–5 by
GPT-4. A prompt is labelled HARD when the small model scored <= 3 — i.e.
when a small model demonstrably wasn't good enough — and EASY otherwise.

Model: ensemble of logistic regressions (MiniLM sentence embedding + word
TF-IDF), logits averaged — the same serving format as the injection
classifier.

A router is judged by a trade-off, not an accuracy number: sending more
traffic to the large model catches more hard prompts but costs more. The
report gives that curve and compares it with random routing, which at
X% of traffic on the large model catches only X% of hard prompts. The
shipped threshold sends hard prompts to the large model with at least
TARGET_HARD_RECALL recall on validation.

Writes backend/app/artifacts/router_classifier.json and
ml/reports/router.json.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from common import (
    SEED,
    binary_report,
    embed,
    embedding_component,
    export_ensemble,
    fetch,
    normalise,
    tfidf_component,
    verify_artifact,
    write_report,
)
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import train_test_split

HARD_MAX_SCORE = 3
TRAIN_SAMPLE = 50_000
TARGET_HARD_RECALL = 0.80

PROBES = [
    ("What is the capital of France?", 0),
    ("Translate 'thank you' into Spanish.", 0),
    ("Give me three synonyms for 'happy'.", 0),
    ("Fix the grammar: 'he go to school yesterday'.", 0),
    ("Prove that there are infinitely many primes p such that p ≡ 3 (mod 4).", 1),
    ("Write a thread-safe LRU cache in Rust with O(1) get/put and explain the ownership model.", 1),
    ("Design a database schema and indexing strategy for a multi-tenant SaaS billing system "
     "with usage-based pricing.", 1),
    ("A train leaves at 3pm at 80 km/h and another at 4pm at 100 km/h from the same station. "
     "When does the second overtake the first, and how far out?", 1),
]


def load() -> tuple[pd.DataFrame, pd.DataFrame]:
    def prep(df: pd.DataFrame) -> pd.DataFrame:
        out = pd.DataFrame({"text": df["prompt"].map(normalise), "score": df["mixtral_score"].astype(int)})
        out = out[out["text"].str.len() >= 3].drop_duplicates("text").reset_index(drop=True)
        out["label"] = (out["score"] <= HARD_MAX_SCORE).astype(int)
        return out

    train = prep(fetch("routellm/gpt4_dataset", "train"))
    train = train.groupby("label", group_keys=False).sample(frac=TRAIN_SAMPLE / len(train), random_state=SEED)
    held = prep(fetch("routellm/gpt4_dataset", "validation"))
    # Drop held-out prompts that also appear in training.
    held = held[~held["text"].isin(set(train["text"]))].reset_index(drop=True)
    return train.reset_index(drop=True), held


class Ensemble:
    def fit(self, texts: pd.Series, X: np.ndarray, y: np.ndarray) -> "Ensemble":
        self.emb = LogisticRegression(C=1.0, class_weight="balanced", max_iter=5000).fit(X, y)
        self.vec = TfidfVectorizer(ngram_range=(1, 2), min_df=3, sublinear_tf=True, max_features=50_000)
        self.word = LogisticRegression(C=1.0, class_weight="balanced", max_iter=3000)
        self.word.fit(self.vec.fit_transform(texts), y)
        return self

    def component_logits(self, texts: pd.Series, X: np.ndarray) -> dict[str, np.ndarray]:
        return {
            "embedding": self.emb.decision_function(X),
            "word": self.word.decision_function(self.vec.transform(texts)),
        }

    def logits(self, texts: pd.Series, X: np.ndarray) -> np.ndarray:
        return np.mean(list(self.component_logits(texts, X).values()), axis=0)


def tradeoff(y: np.ndarray, scores: np.ndarray) -> list[dict]:
    """Share of traffic sent to the large model vs share of hard prompts it catches."""
    order = np.argsort(-scores)
    hard_total = max(1, y.sum())
    rows = []
    for share in (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7):
        k = int(round(share * len(y)))
        rows.append({"to_large": share, "hard_caught": round(float(y[order[:k]].sum() / hard_total), 4)})
    return rows


def main() -> None:
    train, held = load()
    val, test = train_test_split(held, test_size=0.5, stratify=held["label"], random_state=SEED)
    print(f"train {len(train):,} ({train['label'].mean():.1%} hard) / val {len(val):,} / test {len(test):,}")

    X_tr = embed(train["text"].tolist(), "router_train")
    X_va = embed(val["text"].tolist(), "router_val")
    X_te = embed(test["text"].tolist(), "router_test")
    y_tr, y_va, y_te = (d["label"].to_numpy() for d in (train, val, test))

    model = Ensemble().fit(train["text"], X_tr, y_tr)
    val_logits = model.logits(val["text"], X_va)

    # Lowest-cost threshold that still sends >= TARGET_HARD_RECALL of hard prompts to the large model.
    hard_scores = np.sort(val_logits[y_va == 1])
    threshold = float(hard_scores[int(np.floor(len(hard_scores) * (1 - TARGET_HARD_RECALL)))])

    parts = model.component_logits(test["text"], X_te)
    test_logits = np.mean(list(parts.values()), axis=0)
    at_threshold = binary_report(y_te, test_logits, threshold)
    at_threshold["share_to_large"] = round(float((test_logits >= threshold).mean()), 4)

    probe_texts = pd.Series([t for t, _ in PROBES])
    probe_logits = model.logits(probe_texts, embed(probe_texts.tolist(), "router_probes"))
    probes = [
        {"text": t, "expected": "hard" if e else "easy", "routed": "large" if s >= threshold else "small",
         "probability_hard": round(float(1 / (1 + np.exp(-s))), 3)}
        for (t, e), s in zip(PROBES, probe_logits)
    ]

    path = export_ensemble("router_classifier", [
        embedding_component(model.emb),
        tfidf_component(model.vec, model.word),
    ], threshold, {
        "positive_label": "hard",
        "label_rule": f"Mixtral-8x7B answer graded <= {HARD_MAX_SCORE}/5 by GPT-4",
        "datasets": ["routellm/gpt4_dataset"],
        "test_metrics": at_threshold,
    })
    drift = verify_artifact("router_classifier", test["text"].tolist(), X_te, test_logits)

    report = {
        "model": "mean logit of logreg on MiniLM embeddings + word 1-2gram TF-IDF",
        "label_rule": f"hard = small-model answer graded <= {HARD_MAX_SCORE}/5",
        "threshold_logit": round(threshold, 4),
        "threshold_rule": f"lowest-cost threshold with validation hard-prompt recall >= {TARGET_HARD_RECALL:.0%}",
        "split_sizes": {"train": len(train), "val": len(val), "test": len(test)},
        "test_hard_rate": round(float(y_te.mean()), 4),
        "test_roc_auc": round(float(roc_auc_score(y_te, test_logits)), 4),
        "test_roc_auc_by_component": {k: round(float(roc_auc_score(y_te, v)), 4) for k, v in parts.items()},
        "test_at_threshold": at_threshold,
        "test_tradeoff": tradeoff(y_te, test_logits),
        "probes": probes,
        "artifact_bytes": path.stat().st_size,
        "serving_parity_max_logit_diff": drift,
    }
    write_report("router", report)

    print(f"\ntest ROC-AUC {report['test_roc_auc']}  by component {report['test_roc_auc_by_component']}")
    print(f"at threshold: {at_threshold['share_to_large']:.1%} of traffic → large model, "
          f"catching {at_threshold['recall']:.1%} of hard prompts "
          f"(random routing: {at_threshold['share_to_large']:.1%})")
    print("trade-off (share to large model → share of hard prompts caught; random = same as share):")
    for r in report["test_tradeoff"]:
        print(f"  {r['to_large']:.0%} → {r['hard_caught']:.1%}")
    print("probes:")
    for p in probes:
        ok = (p["routed"] == "large") == (p["expected"] == "hard")
        print(f"  [{'OK  ' if ok else 'MISS'}] p(hard)={p['probability_hard']:.2f} → {p['routed']:5}  {p['text'][:70]}")
    print(f"\nartifact → {path} ({path.stat().st_size / 1e6:.1f} MB), serving parity max diff {drift:.1e}")


if __name__ == "__main__":
    main()
