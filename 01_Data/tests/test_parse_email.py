"""WBS 1.3 - parser tests.

Fixtures are modelled on the failure modes actually present in the corpus, found
during WBS 1.1: 141 messages with no body, 40 with unparsable dates, 48 with a
malformed charset parameter (several containing an entire HTML document).
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from parse_email import parse_gmail_payload, parse_raw_message, registered_domain  # noqa: E402


def raw(headers: str, body: str = "") -> bytes:
    return (headers.strip() + "\r\n\r\n" + body).encode("utf-8")


# --------------------------------------------------------------------------- #
# headers
# --------------------------------------------------------------------------- #
def test_basic_sender_extraction():
    rec = parse_raw_message(raw(
        "From: Support Team <support@paypa1-secure.com>\r\n"
        "To: victim@example.com\r\n"
        "Subject: Your account has been limited"))
    assert rec.from_display == "Support Team"
    assert rec.from_address == "support@paypa1-secure.com"
    assert rec.from_registered_domain == "paypa1-secure.com"
    assert rec.subject == "Your account has been limited"


def test_sender_mismatch_detected_via_reply_to():
    rec = parse_raw_message(raw(
        "From: Billing <billing@microsoft.com>\r\n"
        "Reply-To: collect@mail.ru\r\n"
        "Subject: Invoice"))
    assert rec.sender_mismatch is True


def test_no_mismatch_when_reply_to_is_same_registrable_domain():
    rec = parse_raw_message(raw(
        "From: News <news@mail.example.com>\r\n"
        "Reply-To: replies@bounce.example.com\r\n"
        "Subject: Hello"))
    assert rec.sender_mismatch is False


def test_encoded_word_subject_is_decoded():
    rec = parse_raw_message(raw(
        "From: a@b.com\r\nSubject: =?utf-8?B?SGVsbG8gV29ybGQ=?="))
    assert rec.subject == "Hello World"


def test_unparsable_date_is_warned_not_fatal():
    rec = parse_raw_message(raw("From: a@b.com\r\nDate: not a real date\r\nSubject: x"))
    assert "unparsable_date" in rec.parse_warnings
    assert rec.date_iso == ""


def test_valid_date_normalised_to_utc_iso():
    rec = parse_raw_message(raw(
        "From: a@b.com\r\nDate: Tue, 19 Sep 2023 18:35:49 +0000 (UTC)\r\nSubject: x"))
    assert rec.date_iso.startswith("2023-09-19T18:35:49")


# --------------------------------------------------------------------------- #
# degenerate messages
# --------------------------------------------------------------------------- #
def test_empty_body_is_warned():
    rec = parse_raw_message(raw("From: a@b.com\r\nSubject: nothing"))
    assert "empty_body" in rec.parse_warnings
    assert rec.body_char_count == 0


def test_completely_empty_input_does_not_raise():
    rec = parse_raw_message(b"")
    assert rec.from_address == ""
    assert rec.link_count == 0


def test_garbage_input_does_not_raise():
    rec = parse_raw_message(b"\x00\xff\xfe not a message at all")
    assert isinstance(rec.body_text, str)


def test_missing_from_header():
    rec = parse_raw_message(raw("Subject: no sender"))
    assert rec.from_address == ""
    assert rec.from_registered_domain == ""
    assert rec.sender_mismatch is False


# --------------------------------------------------------------------------- #
# links
# --------------------------------------------------------------------------- #
HTML_MISMATCH = (
    '<html><body><p>Click <a href="https://evil-domain.ru/login">'
    'https://www.paypal.com/account</a> now</p></body></html>'
)


def test_display_mismatch_detected():
    rec = parse_raw_message(raw(
        "From: a@b.com\r\nContent-Type: text/html; charset=utf-8", HTML_MISMATCH))
    assert rec.link_count == 1
    assert rec.links[0].registered_domain == "evil-domain.ru"
    assert rec.display_mismatch_count == 1


def test_no_mismatch_when_anchor_text_is_not_a_url():
    rec = parse_raw_message(raw(
        "From: a@b.com\r\nContent-Type: text/html; charset=utf-8",
        '<a href="https://example.com/x">Click here</a>'))
    assert rec.display_mismatch_count == 0


def test_userinfo_obfuscation_resolves_to_real_host():
    rec = parse_raw_message(raw(
        "From: a@b.com", "Visit https://www.paypal.com@evil.example/login now"))
    assert rec.links[0].host == "evil.example"


def test_bare_urls_in_plain_text_are_found():
    rec = parse_raw_message(raw("From: a@b.com", "go to https://a.example and https://b.example"))
    assert rec.link_count == 2
    assert rec.distinct_link_domains == 2


def test_trailing_punctuation_stripped_from_url():
    rec = parse_raw_message(raw("From: a@b.com", "see https://example.com/page."))
    assert rec.links[0].url == "https://example.com/page"


# --------------------------------------------------------------------------- #
# attachments
# --------------------------------------------------------------------------- #
MULTIPART = (
    'From: a@b.com\r\nSubject: invoice\r\n'
    'Content-Type: multipart/mixed; boundary="BOUND"\r\n'
    '\r\n--BOUND\r\nContent-Type: text/plain\r\n\r\nSee attached\r\n'
    '--BOUND\r\nContent-Type: application/pdf\r\n'
    'Content-Disposition: attachment; filename="invoice.pdf"\r\n\r\nPDFBYTES\r\n'
    '--BOUND--\r\n'
)


def test_attachment_recorded_without_payload():
    rec = parse_raw_message(MULTIPART.encode("utf-8"))
    assert rec.attachment_count == 1
    assert rec.attachments[0].filename == "invoice.pdf"
    assert rec.attachments[0].content_type == "application/pdf"
    assert "See attached" in rec.body_text


# --------------------------------------------------------------------------- #
# registrable domain
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("host,expected", [
    ("login.secure.example.co.uk", "example.co.uk"),
    ("www.paypal.com", "paypal.com"),
    ("example.com", "example.com"),
    ("", ""),
])
def test_registered_domain(host, expected):
    assert registered_domain(host) == expected


# --------------------------------------------------------------------------- #
# Gmail path - the contract that matters for WBS 4.2
# --------------------------------------------------------------------------- #
def test_gmail_payload_produces_same_shape():
    rec = parse_gmail_payload({
        "from_display": "Support Team",
        "from_address": "support@paypa1-secure.com",
        "subject": "Your account has been limited",
        "body_html": HTML_MISMATCH,
    })
    assert rec.from_registered_domain == "paypa1-secure.com"
    assert rec.display_mismatch_count == 1
    assert rec.source_corpus == "gmail_dom"


def test_gmail_payload_marks_unavailable_fields():
    rec = parse_gmail_payload({"from_address": "a@b.com", "subject": "x", "body_text": "y"})
    assert "unavailable:received_chain" in rec.parse_warnings
    assert "unavailable:auth_results" in rec.parse_warnings
    assert rec.received_count == 0
    assert rec.auth_results_present is False
    assert rec.return_path_address == ""


def test_gmail_and_corpus_agree_on_the_same_message():
    """The same content through both paths must yield the same inference features."""
    corpus = parse_raw_message(raw(
        "From: Support Team <support@paypa1-secure.com>\r\n"
        "Subject: Act now\r\nContent-Type: text/html; charset=utf-8", HTML_MISMATCH))
    live = parse_gmail_payload({
        "from_display": "Support Team",
        "from_address": "support@paypa1-secure.com",
        "subject": "Act now",
        "body_html": HTML_MISMATCH,
    })
    for field in ("from_registered_domain", "subject", "link_count",
                  "distinct_link_domains", "display_mismatch_count", "body_text"):
        assert getattr(corpus, field) == getattr(live, field), field


def test_empty_gmail_payload_does_not_raise():
    rec = parse_gmail_payload({})
    assert rec.link_count == 0
    assert "empty_body" in rec.parse_warnings
