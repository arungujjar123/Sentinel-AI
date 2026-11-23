# The checks every /v1/chat request passes through before the cache or a
# provider sees it:
#
#   1. PII redaction      — services/redaction.py
#   2. Injection check    — classifier trained in ml/train_injection.py
#   3. Model routing      — classifier trained in ml/train_router.py
#
# The two classifiers share one batch of sentence embeddings of the
# request's user messages, so together they cost one embedding call.
#
# Failure policy:
#   - Redaction errors propagate (the request fails). Sending a prompt
#     whose PII we failed to remove is the outcome this gateway exists to
#     prevent. (A missing NER model is not an error: redaction degrades to
#     emails, phones and cards — see Redactor.)
#   - Classifier errors are logged and the request continues unscored and
#     on the default model. A broken classifier must not take the whole
#     gateway down; the log row's NULL injection_score shows it happened.
from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np

from app.config import settings
from app.services import classifiers
from app.services.embeddings import embed_many
from app.services.redaction import RedactionResult, Redactor

logger = logging.getLogger(__name__)

INJECTION = "injection_classifier"
ROUTER = "router_classifier"

_redactor = Redactor(settings.redaction_ner_model, settings.redaction_allowed_names_list)


@dataclass
class GuardResult:
    redaction: RedactionResult
    injection_score: float | None = None   # max P(injection) over user messages
    blocked: bool = False
    route: str = "default"                 # small | large | pinned | default
    router_score: float | None = None      # P(hard) of the last user message

    @property
    def messages(self) -> list[dict]:
        return self.redaction.messages

    def log_fields(self) -> dict:
        return {
            "injection_score": None if self.injection_score is None else round(self.injection_score, 4),
            "redaction_count": self.redaction.total,
            "redaction_types": self.redaction.types,
            "route": self.route,
            "router_score": None if self.router_score is None else round(self.router_score, 4),
        }


def _threshold(clf: classifiers.EnsembleClassifier, override: float | None) -> float:
    return override if override is not None else clf.probability_threshold


def inspect(messages: list[dict], pinned_model: str | None) -> GuardResult:
    """
    Run every check on a request. Synchronous and CPU-bound (embedding,
    NER) — call it via asyncio.to_thread from async code.
    """
    if settings.redaction_enabled:
        redaction = _redactor.redact(messages)
    else:
        redaction = RedactionResult(messages=[dict(m) for m in messages])
    result = GuardResult(redaction=redaction)

    injection = classifiers.get(INJECTION) if settings.injection_detection_enabled else None
    router = classifiers.get(ROUTER) if settings.routing_enabled and not pinned_model else None
    if pinned_model:
        result.route = "pinned"

    # Classifiers read the original user text, not the redacted copy: they
    # were trained on unredacted prompts, and the text never leaves this
    # process.
    user_texts = [m["content"] for m in messages if m.get("role") == "user" and isinstance(m.get("content"), str)]
    if not user_texts or (injection is None and router is None):
        return result

    try:
        vectors = embed_many(user_texts)
        if injection is not None:
            score = float(np.max(injection.probabilities(user_texts, vectors)))
            result.injection_score = score
            result.blocked = score >= _threshold(injection, settings.injection_threshold)
        if router is not None and not result.blocked:
            p_hard = float(router.probabilities(user_texts[-1:], vectors[-1:])[0])
            result.router_score = p_hard
            result.route = "large" if p_hard >= _threshold(router, settings.router_threshold) else "small"
    except Exception as e:
        logger.error("guardrail classifiers failed, continuing unscored: %s", e)
    return result


def groq_model(guard: GuardResult, pinned_model: str | None) -> str:
    if pinned_model:
        return pinned_model
    return settings.groq_large_model if guard.route == "large" else settings.groq_small_model


def gemini_model(guard: GuardResult) -> str:
    # A pinned request names a Groq model; fall back to the stronger
    # Gemini tier rather than guess at its size.
    return settings.gemini_small_model if guard.route == "small" else settings.gemini_large_model


def large_model_for(provider: str) -> str | None:
    return {"groq": settings.groq_large_model, "gemini": settings.gemini_large_model}.get(provider)


def warmup() -> dict:
    """Load the NER model and both classifiers now instead of on the first request."""
    return {
        "ner": _redactor.warmup() if settings.redaction_enabled else None,
        INJECTION: classifiers.get(INJECTION) is not None,
        ROUTER: classifiers.get(ROUTER) is not None,
    }
