"""Regression tests for defects found in the WBS 1.3/1.4 review (2026-10-06).

Each test here corresponds to a specific defect that was present and shipped
before review. They exist so none of them can come back silently.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import features as F  # noqa: E402
from parse_email import (  # noqa: E402
    domains_in_text, parse_gmail_payload, parse_raw_message, registered_domain, unwrap_redirect,
)


def raw(headers: str, body: str = "") -> bytes:
    return (headers.strip() + "\r\n\r\n" + body).encode("utf-8")


# --- defect: Return-Path drove sender_mismatch (Rule 2 violation) ----------
def test_return_path_does_not_drive_sender_mismatch():
    rec = parse_raw_message(raw(
        "From: Dev List <dev@lists.example.org>\r\n"
        "Return-Path: <dev-bounces@mail-relay.example.net>\r\nSubject: [dev] patch"))
    assert rec.sender_mismatch is False


def test_reply_to_still_drives_sender_mismatch():
    rec = parse_raw_message(raw(
        "From: Billing <billing@microsoft.com>\r\nReply-To: collect@mail.ru\r\nSubject: Invoice"))
    assert rec.sender_mismatch is True


# --- defect: Gmail rewrites every href ------------------------------------
def test_gmail_saferedirect_is_unwrapped():
    assert unwrap_redirect(
        "https://www.google.com/url?q=https%3A%2F%2Fevil.ru%2Flogin&source=gmail"
    ) == "https://evil.ru/login"


def test_rewritten_anchor_resolves_to_the_real_destination():
    html = ('<a href="https://www.google.com/url?q=https%3A%2F%2Fevil.ru%2Fx&amp;source=gmail" '
            'data-saferedirecturl="https://evil.ru/x">Sign in</a>')
    rec = parse_gmail_payload({"from_address": "a@b.com", "subject": "x", "body_html": html})
    assert rec.links[0].registered_domain == "evil.ru"


# --- defect: display mismatch only caught scheme-prefixed anchor text ------
def test_bare_domain_anchor_text_counts_as_mismatch():
    rec = parse_raw_message(raw(
        "From: a@b.com\r\nContent-Type: text/html; charset=utf-8",
        '<a href="https://evil.ru/x">www.paypal.com</a>'))
    assert rec.display_mismatch_count == 1


def test_non_domain_anchor_text_is_not_a_false_mismatch():
    rec = parse_raw_message(raw(
        "From: a@b.com\r\nContent-Type: text/html; charset=utf-8",
        '<a href="https://evil.ru/x">invoice.pdf</a>'))
    assert rec.display_mismatch_count == 0


def test_anchor_display_url_is_not_counted_as_a_second_link():
    rec = parse_raw_message(raw(
        "From: a@b.com\r\nContent-Type: text/html; charset=utf-8",
        '<a href="https://evil.ru/x">https://www.paypal.com/account</a>'))
    assert rec.link_count == 1
    assert "paypal.com" not in {lk.registered_domain for lk in rec.links}


# --- defect: inline images counted as attachments -------------------------
def test_inline_image_is_not_an_attachment():
    msg = ('From: a@b.com\r\nContent-Type: multipart/related; boundary="B"\r\n\r\n'
           '--B\r\nContent-Type: text/html\r\n\r\n<p>hi</p>\r\n'
           '--B\r\nContent-Type: image/gif\r\nContent-ID: <img1>\r\n'
           'Content-Disposition: inline; filename="spacer.gif"\r\n\r\nGIF\r\n--B--\r\n')
    assert parse_raw_message(msg.encode()).attachment_count == 0


# --- defect: message/rfc822 skipped, its body merged into the parent -------
def test_attached_message_is_an_attachment_not_body_text():
    inner = "From: x@y.com\r\nSubject: inner\r\n\r\nSECRET INNER BODY TEXT\r\n"
    msg = ('From: a@b.com\r\nContent-Type: multipart/mixed; boundary="B"\r\n\r\n'
           '--B\r\nContent-Type: text/plain\r\n\r\nouter\r\n'
           '--B\r\nContent-Type: message/rfc822\r\n'
           'Content-Disposition: attachment; filename="m.eml"\r\n\r\n' + inner + '--B--\r\n')
    rec = parse_raw_message(msg.encode())
    assert rec.attachment_count == 1
    assert "SECRET INNER BODY TEXT" not in rec.body_text


# --- defect: IP literals got a fabricated registrable domain --------------
def test_ip_literal_has_no_registrable_domain():
    assert registered_domain("192.168.10.5") == "192.168.10.5"


# --- defect: the corpus anonymisation token leaked into text --------------
def test_anonymisation_token_is_stripped():
    rec = parse_raw_message(raw("From: a@b.com\r\nSubject: hello phishing@pot",
                                "write to phishing@pot today"))
    assert "phishing@pot" not in rec.subject
    assert "phishing@pot" not in rec.body_text


# --- the contract that matters: both paths, same vector -------------------
def test_paths_agree_on_a_message_with_every_divergent_field_present():
    """Earlier agreement tests used a message with none of the fields that
    actually diverge. This one includes all of them."""
    html = '<a href="https://evil.ru/x">www.paypal.com</a>'
    corpus = parse_raw_message(raw(
        "From: PayPal <service@evil.ru>\r\nSubject: Act now\r\n"
        "Return-Path: <bounce@elsewhere.example>\r\n"
        "List-Unsubscribe: <mailto:u@x.example>\r\n"
        "Received: from a by b; Tue, 1 Jan 2002 00:00:00 +0000\r\n"
        "To: zzzz@localhost.netnoteinc.com\r\n"
        "Content-Type: text/html; charset=utf-8", html))
    live = parse_gmail_payload({"from_display": "PayPal", "from_address": "service@evil.ru",
                                "subject": "Act now", "body_html": html,
                                "body_text": "www.paypal.com"})
    assert F.to_vector(corpus) == F.to_vector(live)


def test_domains_in_text_requires_a_public_suffix():
    assert domains_in_text("see www.paypal.com") == {"paypal.com"}
    assert domains_in_text("open invoice.pdf and notes.docx") == set()
