# PII redaction — runs before a prompt reaches the cache, a provider, or
# the request log, so personal data never leaves the gateway.
#
# Detected:
#   PERSON  names, via spaCy NER (model set by REDACTION_NER_MODEL)
#   EMAIL   regex
#   CARD    13–19 digit runs that pass the Luhn checksum
#   PHONE   10–15 digit phone-shaped runs (checked after CARD, so a card
#           number is never misfiled as a phone number)
#
# Each distinct value becomes a numbered placeholder ("[PERSON_1]"),
# stable across all messages in the request so the model can still follow
# who is who. restore() swaps placeholders in the provider's answer back
# to the original values; the mapping lives only in memory for the
# duration of the request.
#
# Because two customers asking the same question now produce the same
# redacted prompt, redaction also raises the semantic cache's hit rate —
# and the cached answer still holds placeholders, restored per request.
#
# Trade-off: NER can't tell a customer's name from a public figure's, so
# "Explain Einstein's theory of relativity" reaches the model as
# "Explain [PERSON_1]'s theory…" and the answer suffers. The default is
# privacy-first (redact every name, as Presidio and LLM Guard also do);
# REDACTION_ALLOWED_NAMES lists names an operator decides aren't personal
# data — public figures, product names, NER false positives.
from __future__ import annotations

import logging
import re
import threading
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
# Digits with optional single space/dash separators, not glued to other digits.
_CARD = re.compile(r"(?<![\d-])(?:\d[ -]?){12,18}\d(?![\d-])")
_PHONE = re.compile(r"(?<![\w+])(?:\+\d{1,3}[ .-]?)?(?:\(\d{2,5}\)[ .-]?)?\d(?:[ .-]?\d){8,13}(?!\d)")
_PLACEHOLDER = re.compile(r"\[(PERSON|EMAIL|CARD|PHONE)_(\d+)\]")


def luhn_valid(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


@dataclass
class RedactionResult:
    messages: list[dict]
    mapping: dict[str, str] = field(default_factory=dict)   # placeholder → original
    counts: dict[str, int] = field(default_factory=dict)    # entity type → distinct values

    @property
    def total(self) -> int:
        return sum(self.counts.values())

    @property
    def types(self) -> str | None:
        return ",".join(sorted(self.counts)) or None


class Redactor:
    def __init__(self, ner_model: str | None, allowed_names: list[str] | tuple[str, ...] = ()) -> None:
        self._ner_model = ner_model
        self._allowed = {n.strip().lower() for n in allowed_names if n.strip()}
        self._nlp = None
        self._ner_failed = False
        # Requests run redaction in worker threads (asyncio.to_thread), and
        # spaCy doesn't promise a Language object is safe to call from
        # several threads at once. NER takes a few ms, so serialising it
        # costs nothing next to a model call. Also stops two first
        # requests from loading the model twice.
        self._lock = threading.Lock()

    def _get_nlp(self):
        if self._nlp is None and self._ner_model and not self._ner_failed:
            try:
                import spacy

                self._nlp = spacy.load(
                    self._ner_model, disable=["parser", "lemmatizer", "attribute_ruler", "tagger", "senter"]
                )
            except Exception as e:
                # Names stop being redacted, but emails, phones and cards
                # still are — degrade, never fail the request.
                self._ner_failed = True
                logger.error("NER model %r unavailable, redacting without names: %s", self._ner_model, e)
        return self._nlp

    def warmup(self) -> bool:
        with self._lock:
            return self._get_nlp() is not None

    def _spans(self, text: str, doc) -> list[tuple[int, int, str]]:
        spans: list[tuple[int, int, str]] = [(m.start(), m.end(), "EMAIL") for m in _EMAIL.finditer(text)]
        for m in _CARD.finditer(text):
            digits = re.sub(r"\D", "", m.group())
            if 13 <= len(digits) <= 19 and luhn_valid(digits):
                spans.append((m.start(), m.end(), "CARD"))
        for m in _PHONE.finditer(text):
            if 10 <= len(re.sub(r"\D", "", m.group())) <= 15:
                spans.append((m.start(), m.end(), "PHONE"))
        if doc is not None:
            spans += [
                (e.start_char, e.end_char, "PERSON")
                for e in doc.ents
                if e.label_ == "PERSON" and e.text.lower() not in self._allowed
            ]

        # Earlier entries win on overlap: email, card, phone, then names —
        # a regex match is exact where NER is a guess.
        kept: list[tuple[int, int, str]] = []
        for s in spans:
            if all(s[1] <= k[0] or s[0] >= k[1] for k in kept):
                kept.append(s)
        return sorted(kept)

    def redact(self, messages: list[dict]) -> RedactionResult:
        """Redact every message's content. System prompts can hold PII too (e.g. a customer record)."""
        contents = [m.get("content") if isinstance(m.get("content"), str) else "" for m in messages]
        with self._lock:
            nlp = self._get_nlp()
            docs = list(nlp.pipe(contents)) if nlp is not None else [None] * len(contents)

        result = RedactionResult(messages=[])
        assigned: dict[tuple[str, str], str] = {}
        for msg, text, doc in zip(messages, contents, docs):
            out, last = [], 0
            for start, end, kind in self._spans(text, doc):
                value = text[start:end]
                key = (kind, value.lower() if kind in ("PERSON", "EMAIL") else re.sub(r"\D", "", value))
                if key not in assigned:
                    n = result.counts.get(kind, 0) + 1
                    result.counts[kind] = n
                    assigned[key] = f"[{kind}_{n}]"
                    result.mapping[assigned[key]] = value
                out.append(text[last:start])
                out.append(assigned[key])
                last = end
            out.append(text[last:])
            result.messages.append({**msg, "content": "".join(out)})
        return result


def restore(text: str, mapping: dict[str, str]) -> str:
    """Put original values back into a provider response. Unknown placeholders are left as-is."""
    if not mapping or not text:
        return text
    return _PLACEHOLDER.sub(lambda m: mapping.get(m.group(0), m.group(0)), text)
