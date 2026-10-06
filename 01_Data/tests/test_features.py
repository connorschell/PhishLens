"""WBS 1.4 - feature extractor tests.

The design rules in features.py are only real if something enforces them, so the
first two tests here are about what the extractor must *not* do.
"""

import inspect
import sys

import pytest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import features as F  # noqa: E402
from parse_email import parse_gmail_payload, parse_raw_message  # noqa: E402
from record_schema import EmailRecord  # noqa: E402


def raw(headers: str, body: str = "") -> bytes:
    return (headers.strip() + "\r\n\r\n" + body).encode("utf-8")


# --------------------------------------------------------------------------- #
# the rules
# --------------------------------------------------------------------------- #
def test_extractor_never_reads_forbidden_fields():
    """Rules 2 and 3: no Gmail-unavailable fields, no corpus giveaways."""
    source = inspect.getsource(F.extract_features)
    for field in F.FORBIDDEN_FIELDS:
        assert f"rec.{field}" not in source, f"extract_features reads forbidden field {field}"


def test_forbidden_fields_cannot_reach_the_vector_indirectly():
    """The grep above only sees one function. A forbidden field read in the
    PARSER and surfaced through a derived field would slip past it - which is
    exactly what happened: sender_mismatch was built from Return-Path, so
    `sender_reply_to_mismatch` carried a field the Gmail page never supplies.

    This test parses real messages that differ ONLY in forbidden fields and
    asserts the feature vector cannot tell them apart.
    """
    base = "From: Alice <alice@example.com>\r\nSubject: Quarterly report\r\n"
    body = "The numbers are attached. See https://example.com/q3 for detail."
    plain = parse_raw_message(raw(base, body))
    for extra in (
        "Return-Path: <bounce@some-list.example.org>\r\n",
        "Received: from a.example by b.example; Tue, 1 Jan 2002 00:00:00 +0000\r\n",
        "Authentication-Results: mx.example; spf=pass\r\n",
        "List-Unsubscribe: <mailto:x@y.example>\r\n",
        "To: zzzz@localhost.netnoteinc.com\r\n",
        "Message-ID: <abc123@mail.example>\r\n",
        "Date: Thu, 22 Aug 2002 12:36:23 +0100\r\n",
    ):
        other = parse_raw_message(raw(base + extra, body))
        assert F.extract_features(plain) == F.extract_features(other), extra.split(":")[0]


def test_corpus_provenance_cannot_change_the_vector_via_parser():
    """Same content, dressed as each corpus. Vectors must be identical."""
    body = "Dear Customer, verify your account at https://secure-login.top/go"
    phish_style = parse_raw_message(raw(
        "From: Service <no-reply@secure-login.top>\r\nSubject: Account notice\r\n"
        "To: phishing@pot\r\nDate: Tue, 19 Sep 2023 18:35:49 +0000\r\n"
        "Return-Path: <r@secure-login.top>\r\n", body))
    ham_style = parse_raw_message(raw(
        "From: Service <no-reply@secure-login.top>\r\nSubject: Account notice\r\n"
        "To: zzzz@localhost.netnoteinc.com\r\n"
        "Date: Thu, 22 Aug 2002 12:36:23 +0100\r\n"
        "List-Unsubscribe: <mailto:u@x.example>\r\n", body))
    assert F.extract_features(phish_style) == F.extract_features(ham_style)


def test_corpus_provenance_cannot_change_the_vector():
    """Two records identical except for corpus, label, recipient and date must
    produce identical features. If they don't, the model can learn which corpus
    a message came from instead of whether it is phishing."""
    common = dict(from_display="Support", from_address="a@example.com",
                  from_registered_domain="example.com", subject="Hello",
                  body_text="Some body text here", body_word_count=4)
    a = EmailRecord(record_id="1", source_corpus="phishing_pot", source_group="email",
                    source_path="x", label="phish", to_address="phishing@pot",
                    date_iso="2023-09-19T00:00:00+00:00", received_count=5,
                    auth_results_present=True, return_path_address="r@evil.test", **common)
    b = EmailRecord(record_id="2", source_corpus="spamassassin", source_group="easy-ham-1",
                    source_path="y", label="ham", to_address="zzzz@localhost.netnoteinc.com",
                    date_iso="2002-08-22T00:00:00+00:00", received_count=0,
                    auth_results_present=False, return_path_address="", **common)
    assert F.extract_features(a) == F.extract_features(b)


def test_vector_length_and_order_are_stable():
    rec = parse_raw_message(raw("From: a@b.com\r\nSubject: x", "body"))
    v = F.to_vector(rec)
    assert len(v) == len(F.FEATURE_NAMES) == 43
    assert all(isinstance(x, float) for x in v)


def test_every_feature_is_finite_on_degenerate_input():
    import math
    for rec in (parse_raw_message(b""), parse_gmail_payload({}),
                parse_raw_message(raw("From: a@b.com"))):
        for name, val in F.extract_features(rec).items():
            assert math.isfinite(val), f"{name} is not finite"


# --------------------------------------------------------------------------- #
# individual signals
# --------------------------------------------------------------------------- #
def test_brand_claimed_but_sender_unrelated():
    rec = parse_raw_message(raw(
        "From: PayPal Service <no-reply@secure-billing-update.top>\r\nSubject: Notice"))
    f = F.extract_features(rec)
    assert f["brand_claimed_in_display_or_subject"] == 1.0
    assert f["brand_claimed_but_sender_unrelated"] == 1.0
    assert f["sender_domain_suspicious_tld"] == 1.0


def test_real_brand_sender_does_not_trip_impersonation():
    rec = parse_raw_message(raw("From: PayPal <service@paypal.com>\r\nSubject: Your receipt"))
    f = F.extract_features(rec)
    assert f["brand_claimed_in_display_or_subject"] == 1.0
    assert f["brand_claimed_but_sender_unrelated"] == 0.0


def test_display_mismatch_feature():
    rec = parse_raw_message(raw(
        "From: a@b.com\r\nContent-Type: text/html; charset=utf-8",
        '<a href="https://evil.ru/x">https://www.paypal.com/account</a>'))
    f = F.extract_features(rec)
    assert f["has_link_display_mismatch"] == 1.0


def test_link_domain_matches_sender():
    rec = parse_raw_message(raw("From: news@example.com", "visit https://example.com/offers"))
    f = F.extract_features(rec)
    assert f["link_domain_matches_sender"] == 1.0
    assert f["no_link_matches_sender_domain"] == 0.0


def test_ip_literal_and_shortener_and_punycode():
    rec = parse_raw_message(raw("From: a@b.com",
                                "http://192.168.10.5/login https://bit.ly/abc https://xn--80ak6aa92e.com/"))
    f = F.extract_features(rec)
    assert f["has_ip_literal_link"] == 1.0
    assert f["has_url_shortener"] == 1.0
    assert f["has_punycode_link"] == 1.0
    assert f["has_http_only_link"] == 1.0


def test_language_features():
    rec = parse_raw_message(raw(
        "From: a@b.com\r\nSubject: URGENT ACTION REQUIRED!!",
        "Dear Customer, your account has been suspended. Verify your account "
        "immediately or it expires. Confirm your identity to restore billing."))
    f = F.extract_features(rec)
    assert f["urgency_term_count"] >= 2
    assert f["threat_term_count"] >= 1
    assert f["credential_term_count"] >= 1
    assert f["has_generic_greeting"] == 1.0
    assert f["subject_exclamation_count"] == 2.0
    assert f["subject_allcaps_word_count"] == 3.0


def test_benign_message_is_quiet_across_the_board():
    rec = parse_raw_message(raw(
        "From: Jane Doe <jane@university.edu>\r\nSubject: Lunch tomorrow?",
        "Hi Connor, are you free around noon? Jane"))
    f = F.extract_features(rec)
    for name in ("urgency_term_count", "threat_term_count", "credential_term_count",
                 "has_link_display_mismatch", "brand_claimed_but_sender_unrelated",
                 "has_url_shortener", "has_ip_literal_link"):
        assert f[name] == 0.0, name


@pytest.mark.parametrize("display,subject", [
    ("Yahoo Groups", "weekly digest"),       # "ups" inside "Groups"
    ("Startups Weekly", "news"),             # "ups" again
    ("", "Your purchase receipt"),           # "chase" inside "purchase"
])
def test_brand_matching_does_not_fire_on_substrings(display, subject):
    rec = parse_raw_message(raw(f"From: {display} <x@y.com>\r\nSubject: {subject}"))
    f = F.extract_features(rec)
    assert f["brand_claimed_in_display_or_subject"] == 0.0
    assert f["brand_claimed_but_sender_unrelated"] == 0.0


def test_keyword_matching_does_not_fire_on_substrings():
    rec = parse_raw_message(raw("From: a@b.com\r\nSubject: Please unblock the clock"))
    assert F.extract_features(rec)["threat_term_count"] == 0.0


def test_term_families_counted_once_not_three_times():
    """expire / expires / expiring in one sentence is one reason, not three."""
    rec = parse_raw_message(raw("From: a@b.com\r\nSubject: notice",
                                "Your pass expires soon; it is expiring; it will expire."))
    assert F.extract_features(rec)["urgency_term_count"] <= 2


def test_mime_structure_features_are_gone():
    """They were the strongest separators in the corpus and constant at
    inference. Their absence is a design decision, so it is pinned here."""
    for name in ("has_html_part", "has_text_part", "html_without_text_alternative",
                 "has_list_unsubscribe"):
        assert name not in F.FEATURE_NAMES


def test_cctld_sender_has_no_phantom_subdomain():
    rec = parse_raw_message(raw("From: news@bbc.co.uk\r\nSubject: x"))
    assert F.extract_features(rec)["sender_domain_subdomain_depth"] == 0.0


def test_risky_attachment():
    msg = ('From: a@b.com\r\nContent-Type: multipart/mixed; boundary="B"\r\n\r\n'
           '--B\r\nContent-Type: text/plain\r\n\r\nsee attached\r\n'
           '--B\r\nContent-Type: application/octet-stream\r\n'
           'Content-Disposition: attachment; filename="invoice.exe"\r\n\r\nX\r\n--B--\r\n')
    f = F.extract_features(parse_raw_message(msg.encode()))
    assert f["has_risky_attachment"] == 1.0


def test_gmail_and_corpus_paths_give_identical_vectors():
    html = '<a href="https://evil.ru/x">https://www.paypal.com/account</a>'
    corpus = parse_raw_message(raw(
        "From: PayPal <service@evil.ru>\r\nSubject: Act now\r\n"
        "Content-Type: text/html; charset=utf-8", html))
    live = parse_gmail_payload({"from_display": "PayPal", "from_address": "service@evil.ru",
                               "subject": "Act now", "body_html": html})
    assert F.to_vector(corpus) == F.to_vector(live)
