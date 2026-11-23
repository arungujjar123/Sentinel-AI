"""PII redaction: regex entities, Luhn filtering, placeholder stability, restore."""
import pytest

from app.services.redaction import Redactor, luhn_valid, restore


@pytest.fixture(scope="module")
def regex_only():
    return Redactor(ner_model=None)


def _one(redactor, text):
    return redactor.redact([{"role": "user", "content": text}])


def test_luhn():
    assert luhn_valid("4111111111111111")
    assert not luhn_valid("4111111111111112")


def test_email_phone_and_card_are_replaced(regex_only):
    r = _one(regex_only, "Mail a.b@example.com or call +91 98765 43210, card 4111 1111 1111 1111.")
    content = r.messages[0]["content"]
    assert content == "Mail [EMAIL_1] or call [PHONE_1], card [CARD_1]."
    assert r.counts == {"EMAIL": 1, "PHONE": 1, "CARD": 1}
    assert r.mapping["[CARD_1]"] == "4111 1111 1111 1111"


def test_digit_run_failing_luhn_is_not_a_card(regex_only):
    # 16 digits, invalid checksum: an order number, not a card. Too long to be a phone.
    r = _one(regex_only, "Order 1234567812345678 shipped.")
    assert "CARD" not in r.counts
    assert "[CARD_" not in r.messages[0]["content"]


@pytest.mark.parametrize("text", [
    "The meeting is at 10:30 on 2024-05-12.",
    "Version 3.12.1 fixed 404 errors on port 8080.",
    "Revenue grew 1500 percent.",
])
def test_ordinary_numbers_survive(regex_only, text):
    assert _one(regex_only, text).messages[0]["content"] == text


def test_same_value_gets_same_placeholder_across_messages(regex_only):
    r = regex_only.redact([
        {"role": "system", "content": "Customer email: x@y.io"},
        {"role": "user", "content": "Reply to x@y.io and cc z@y.io"},
    ])
    assert r.messages[0]["content"] == "Customer email: [EMAIL_1]"
    assert r.messages[1]["content"] == "Reply to [EMAIL_1] and cc [EMAIL_2]"
    assert r.counts == {"EMAIL": 2}


def test_non_content_fields_are_preserved(regex_only):
    r = regex_only.redact([{"role": "user", "content": "hi"}])
    assert r.messages == [{"role": "user", "content": "hi"}]
    assert r.total == 0 and r.types is None


def test_restore_swaps_known_placeholders_only():
    mapping = {"[PERSON_1]": "Priya Sharma", "[EMAIL_1]": "p@x.com"}
    assert restore("Dear [PERSON_1], we wrote to [EMAIL_1]. [PERSON_2]?", mapping) == \
        "Dear Priya Sharma, we wrote to p@x.com. [PERSON_2]?"
    assert restore("no placeholders", mapping) == "no placeholders"


def test_missing_ner_model_degrades_to_regex():
    r = Redactor(ner_model="definitely_not_a_spacy_model")
    out = _one(r, "John Smith, john@smith.dev")
    assert out.messages[0]["content"] == "John Smith, [EMAIL_1]"


@pytest.fixture(scope="module")
def ner_model():
    """The gateway's default NER model (installed by requirements.txt); skip if absent."""
    from app.config import settings

    spacy = pytest.importorskip("spacy")
    try:
        spacy.load(settings.redaction_ner_model)
    except OSError:
        pytest.skip(f"{settings.redaction_ner_model} not installed")
    return settings.redaction_ner_model


def test_names_are_redacted_when_ner_is_available(ner_model):
    r = _one(Redactor(ner_model), "Hi, I am Priya Sharma and John Smith will call you.")
    assert r.messages[0]["content"] == "Hi, I am [PERSON_1] and [PERSON_2] will call you."
    assert r.counts == {"PERSON": 2}


def test_allowed_names_are_kept(ner_model):
    r = Redactor(ner_model, allowed_names=["john smith"])
    out = _one(r, "Hi, I am Priya Sharma and John Smith will call you.")
    assert out.messages[0]["content"] == "Hi, I am [PERSON_1] and John Smith will call you."
