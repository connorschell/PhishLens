"""WBS 1.3 - the email parser.

One parser, two inputs. A message read from a corpus file and a message scraped
out of the Gmail web page both come out the other side as the same
``EmailRecord``, so the model sees one shape at training time and at inference
time.

    parse_raw_message(raw_bytes, ...)  -> EmailRecord     # corpus (.eml, RFC 822)
    parse_gmail_payload(payload, ...)  -> EmailRecord     # live Gmail DOM scrape

The Gmail path exists because the extension (WBS 4.2) cannot hand us a raw
message. It can only read what the rendered page shows. That path therefore
produces a record with fewer fields populated, and the schema marks which ones -
see ``AVAILABILITY: corpus-only`` in record_schema.py. The feature extractor
(WBS 1.4) refuses to use those fields for exactly this reason.
"""

from __future__ import annotations

import email
import email.policy
import hashlib
import re
import sys
from email.header import decode_header, make_header
from email.utils import parseaddr, parsedate_to_datetime
from datetime import timezone
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup

try:
    import tldextract

    _EXTRACT = tldextract.TLDExtract(suffix_list_urls=())  # offline: bundled snapshot
except Exception:  # pragma: no cover
    _EXTRACT = None

sys.path.insert(0, str(Path(__file__).resolve().parent))
from record_schema import SCHEMA_VERSION, Attachment, EmailRecord, Link  # noqa: E402

URL_RE = re.compile(r"""https?://[^\s<>"'\])}]+""", re.IGNORECASE)
BARE_DOMAIN_RE = re.compile(r"\b(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,}\b", re.IGNORECASE)
WS_RE = re.compile(r"\s+")

# The phishing corpus replaces every recipient address with this token. It is a
# perfect marker of which corpus a message came from, so it is removed from the
# text rather than left to poison any future text feature or the near-duplicate
# fingerprint.
ANON_TOKENS = ("phishing@pot",)


# --------------------------------------------------------------------------- #
# shared helpers
# --------------------------------------------------------------------------- #
def decode_hdr(value: object | None) -> str:
    """Decode RFC 2047 encoded-words, coercing whatever we were handed to str.

    Header values arrive as str or email.header.Header, and malformed corpus
    messages produce both.
    """
    if not value:
        return ""
    value = str(value)
    try:
        return str(make_header(decode_header(value))).strip()
    except Exception:
        return value.strip()


IP_HOST_RE = re.compile(r"^\d{1,3}(\.\d{1,3}){3}$")


def registered_domain(host: str) -> str:
    """Return the registrable domain, e.g. login.secure.example.co.uk -> example.co.uk."""
    if not host:
        return ""
    host = host.strip().strip(".").lower()
    if IP_HOST_RE.match(host):
        return host  # an IP literal has no registrable domain; "10.5" would be a lie
    if _EXTRACT is not None:
        parts = _EXTRACT(host)
        if parts.domain and parts.suffix:
            return f"{parts.domain}.{parts.suffix}"
    # Unknown public suffix: fall back to the last two labels rather than the
    # bare domain label, which would collapse a.newtld and b.newtld together.
    # The bundled suffix snapshot is frozen, so genuinely new TLDs land here.
    bits = host.split(".")
    return ".".join(bits[-2:]) if len(bits) >= 2 else host


def host_of(url: str) -> str:
    m = re.match(r"^\s*([a-z][a-z0-9+.-]*)://([^/?#\s]+)", url, re.IGNORECASE)
    if not m:
        return ""
    netloc = m.group(2).split("@")[-1]  # drop userinfo - a classic obfuscation
    return netloc.split(":")[0].lower()


def scheme_of(url: str) -> str:
    m = re.match(r"^\s*([a-z][a-z0-9+.-]*)://", url, re.IGNORECASE)
    return m.group(1).lower() if m else ""


def domain_of_address(addr: str) -> str:
    return addr.split("@")[-1].strip().lower() if "@" in addr else ""


SAFEREDIRECT_RE = re.compile(
    r"^https?://(?:www\.)?google\.com/url\?(?:[^#]*&)?q=([^&#]+)", re.IGNORECASE)


def unwrap_redirect(href: str) -> str:
    """Undo Gmail's outbound link rewriting.

    The Gmail web client rewrites anchors to
    https://www.google.com/url?q=<target>&source=gmail... and keeps the original
    in data-saferedirecturl. Left alone, every link in a live message would
    report its host as www.google.com, which would silently destroy every
    link-based feature at inference time while training looked fine.
    """
    m = SAFEREDIRECT_RE.match(href or "")
    if not m:
        return href
    from urllib.parse import unquote
    return unquote(m.group(1))


def domains_in_text(text: str) -> set[str]:
    """Registrable domains named in visible text, with or without a scheme.

    Phishing usually renders the impersonated address as bare text -
    "www.paypal.com", not "https://www.paypal.com" - so matching only on full
    URLs misses most display mismatches. A public suffix is required, which
    keeps strings like "invoice.pdf" out.
    """
    out: set[str] = set()
    for url in URL_RE.findall(text):
        d = registered_domain(host_of(url))
        if d:
            out.add(d)
    for token in BARE_DOMAIN_RE.findall(text or ""):
        token = token.strip(".").lower()
        if _EXTRACT is not None:
            parts = _EXTRACT(token)
            if parts.domain and parts.suffix:
                out.add(f"{parts.domain}.{parts.suffix}")
    out.discard("")
    return out


def html_to_text(html: str) -> tuple[str, list[tuple[str, str]]]:
    """Return (visible text, [(href, anchor text)]), with redirects unwrapped."""
    try:
        soup = BeautifulSoup(html, "lxml")  # ~3x faster than html.parser on real mail
    except Exception:
        soup = BeautifulSoup(html, "html.parser")
    anchors = []
    for a in soup.find_all("a"):
        # data-saferedirecturl holds the original when Gmail has rewritten href.
        href = (a.get("data-saferedirecturl") or a.get("href") or "").strip()
        href = unwrap_redirect(href)
        if href:
            anchors.append((href, a.get_text(" ", strip=True)))
    for tag in soup(["script", "style", "head"]):
        tag.decompose()
    return soup.get_text(" ", strip=True), anchors


def build_links(anchors: list[tuple[str, str]], body_text: str) -> list[Link]:
    """Turn anchors and bare URLs into Link records, flagging display mismatch.

    An anchor whose visible text names one domain while its href points at
    another is the single most recognisable phishing tell, so it is computed
    here rather than left to the feature extractor.
    """
    links: list[Link] = []
    seen: set[str] = set()

    for href, anchor_text in anchors:
        if not href.lower().startswith(("http://", "https://")):
            continue
        host = host_of(href)
        reg = registered_domain(host)
        anchor_urls = URL_RE.findall(anchor_text)
        anchor_domains = domains_in_text(anchor_text)
        # The visible text of an anchor is not itself a destination. A message
        # displaying "https://www.paypal.com/account" while linking to
        # evil-domain.ru must not be credited with a link to paypal.com, so
        # these are suppressed before the bare-URL scan below.
        for u in anchor_urls:
            seen.add(u)
            seen.add(u.rstrip(".,;:!?"))
        links.append(
            Link(
                url=href[:2048],
                host=host,
                registered_domain=reg,
                scheme=scheme_of(href),
                display_text=anchor_text[:200],
                in_html=True,
                display_mismatch=bool(anchor_domains and reg and reg not in anchor_domains),
            )
        )
        seen.add(href)

    for url in URL_RE.findall(body_text):
        url = url.rstrip(".,;:!?")
        if url in seen:
            continue
        seen.add(url)
        host = host_of(url)
        links.append(
            Link(
                url=url[:2048],
                host=host,
                registered_domain=registered_domain(host),
                scheme=scheme_of(url),
                in_html=False,
            )
        )
    return links


def strip_anon_tokens(text: str) -> str:
    for token in ANON_TOKENS:
        text = text.replace(token, "")
    return text


def _finalise(rec: EmailRecord, body: str, links: list[Link], warnings: list[str]) -> EmailRecord:
    body = WS_RE.sub(" ", strip_anon_tokens(body)).strip()
    rec.subject = strip_anon_tokens(rec.subject).strip()
    rec.body_text = body
    rec.body_char_count = len(body)
    rec.body_word_count = len(body.split())
    rec.links = links
    rec.link_count = len(links)
    rec.distinct_link_domains = len({lk.registered_domain for lk in links if lk.registered_domain})
    rec.display_mismatch_count = sum(1 for lk in links if lk.display_mismatch)
    rec.attachment_count = len(rec.attachments)
    # Reply-To only. Return-Path is not visible in Gmail's rendered page, and in
    # the 2002 ham corpus it is the mailing-list bounce address, which made this
    # fire on 62% of legitimate mail versus 19% of phishing - an inverted
    # corpus-era artifact rather than a phishing signal.
    reply_reg = registered_domain(rec.reply_to_domain)
    rec.sender_mismatch = bool(
        rec.from_registered_domain and reply_reg and reply_reg != rec.from_registered_domain
    )
    if not body and not rec.attachments:
        warnings.append("empty_body")
    rec.parse_warnings = sorted(set(warnings))
    return rec


# --------------------------------------------------------------------------- #
# corpus path
# --------------------------------------------------------------------------- #
def parse_raw_message(
    raw: bytes,
    source_corpus: str = "",
    source_group: str = "",
    source_path: str = "",
    label: str = "",
) -> EmailRecord:
    """Parse a raw RFC 822 message into an EmailRecord."""
    warnings: list[str] = []
    try:
        msg = email.message_from_bytes(raw, policy=email.policy.compat32)
    except Exception as exc:
        warnings.append(f"parse_failed:{type(exc).__name__}")
        msg = email.message_from_string("", policy=email.policy.compat32)

    rec = EmailRecord(
        record_id=hashlib.sha256(raw).hexdigest()[:24],
        source_corpus=source_corpus,
        source_group=source_group,
        source_path=source_path,
        label=label,
        schema_version=SCHEMA_VERSION,
    )

    from_display, from_addr = parseaddr(decode_hdr(msg.get("From")))
    rec.from_display = from_display
    rec.from_address = from_addr.lower()
    rec.from_domain = domain_of_address(rec.from_address)
    rec.from_registered_domain = registered_domain(rec.from_domain)

    _, reply_to = parseaddr(decode_hdr(msg.get("Reply-To")))
    rec.reply_to_address = reply_to.lower()
    rec.reply_to_domain = domain_of_address(rec.reply_to_address)

    _, return_path = parseaddr(decode_hdr(msg.get("Return-Path")))
    rec.return_path_address = return_path.lower()

    _, to_addr = parseaddr(decode_hdr(msg.get("To")))
    rec.to_address = to_addr.lower()
    rec.subject = decode_hdr(msg.get("Subject"))
    rec.message_id = decode_hdr(msg.get("Message-ID"))
    rec.date_raw = decode_hdr(msg.get("Date"))
    if rec.date_raw:
        try:
            dt = parsedate_to_datetime(rec.date_raw)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            rec.date_iso = dt.astimezone(timezone.utc).isoformat(timespec="seconds")
        except Exception:
            warnings.append("unparsable_date")

    rec.received_count = len(msg.get_all("Received") or [])
    rec.auth_results_present = any(
        msg.get(h) for h in ("Authentication-Results", "Received-SPF", "DKIM-Signature")
    )
    rec.list_unsubscribe_present = bool(msg.get("List-Unsubscribe"))

    text_parts: list[str] = []
    html_parts: list[str] = []
    skip_subtrees: list = []
    for part in msg.walk():
        if any(part is sub or part in sub.walk() for sub in skip_subtrees):
            continue
        ctype = (part.get_content_type() or "").lower()
        disposition = str(part.get("Content-Disposition") or "").lower()
        filename = decode_hdr(part.get_filename())

        # An attached .eml is multipart, so it has to be caught before the
        # multipart skip below - otherwise walk() descends into it and its body
        # text is merged into the parent message.
        if ctype == "message/rfc822" or (part.is_multipart() and "attachment" in disposition):
            rec.attachments.append(
                Attachment(filename=filename or "(attached message)",
                           content_type=ctype or "message/rfc822", size_bytes=0))
            skip_subtrees.append(part)
            continue
        if part.is_multipart():
            continue

        # "inline" parts are embedded images and tracking pixels, which Gmail
        # does not present as attachments. Only real attachments count.
        if "attachment" in disposition or (filename and "inline" not in disposition
                                           and not part.get("Content-ID")):
            payload = part.get_payload(decode=True) or b""
            rec.attachments.append(
                Attachment(
                    filename=filename or "(unnamed)",
                    content_type=ctype,
                    size_bytes=len(payload),
                )
            )
            continue

        payload = part.get_payload(decode=True)
        if payload is None:
            continue
        charset = part.get_content_charset() or "utf-8"
        try:
            # Strict first: errors="replace" can never raise, so decoding
            # straight to replacement characters hides the failure entirely.
            text = payload.decode(charset)
        except (LookupError, UnicodeDecodeError):
            try:
                text = payload.decode("utf-8")
            except UnicodeDecodeError:
                text = payload.decode("latin-1", errors="replace")
            # Malformed messages put entire HTML documents in the charset
            # parameter, so the label is clipped before it becomes a report key.
            label_ = re.sub(r"[^A-Za-z0-9_.:-]", "", str(charset))[:24] or "unknown"
            warnings.append(f"charset_fallback:{label_}")

        if ctype == "text/plain":
            text_parts.append(text)
        elif ctype == "text/html":
            html_parts.append(text)

    rec.has_text_part = bool(text_parts)
    rec.has_html_part = bool(html_parts)

    anchors: list[tuple[str, str]] = []
    for html in html_parts:
        visible, found = html_to_text(html)
        anchors.extend(found)
        if not text_parts:
            text_parts.append(visible)

    body = WS_RE.sub(" ", "\n".join(text_parts)).strip()
    return _finalise(rec, body, build_links(anchors, body), warnings)


# --------------------------------------------------------------------------- #
# live Gmail path
# --------------------------------------------------------------------------- #
GMAIL_PAYLOAD_FIELDS = ("from_display", "from_address", "reply_to_address", "subject", "body_html",
                        "body_text", "attachments")


def parse_gmail_payload(payload: dict[str, Any], record_id: str = "") -> EmailRecord:
    """Parse a payload scraped from the Gmail web page into the same EmailRecord.

    The extension sends what the rendered page exposes. Fields the DOM cannot
    supply stay at their defaults and are recorded in parse_warnings, so a record
    never silently claims a signal it does not have:

        return_path_address, received_count, auth_results_present

    ``payload`` keys (all optional): from_display, from_address, reply_to_address,
    subject, body_html, body_text, attachments (list of {filename, content_type,
    size_bytes}).
    """
    warnings = ["source:gmail_dom", "unavailable:return_path", "unavailable:received_chain",
                "unavailable:auth_results"]

    raw_id = record_id or hashlib.sha256(
        f"{payload.get('from_address','')}|{payload.get('subject','')}|"
        f"{(payload.get('body_text') or payload.get('body_html') or '')[:2000]}".encode(
            "utf-8", errors="replace")
    ).hexdigest()[:24]

    rec = EmailRecord(
        record_id=raw_id,
        source_corpus="gmail_dom",
        source_group="live",
        source_path="",
        label="",
        schema_version=SCHEMA_VERSION,
    )

    rec.from_display = str(payload.get("from_display") or "").strip()
    rec.from_address = str(payload.get("from_address") or "").strip().lower()
    rec.from_domain = domain_of_address(rec.from_address)
    rec.from_registered_domain = registered_domain(rec.from_domain)
    rec.reply_to_address = str(payload.get("reply_to_address") or "").strip().lower()
    rec.reply_to_domain = domain_of_address(rec.reply_to_address)
    rec.subject = str(payload.get("subject") or "").strip()

    body_html = payload.get("body_html") or ""
    body_text = payload.get("body_text") or ""
    anchors: list[tuple[str, str]] = []
    if body_html:
        rec.has_html_part = True
        visible, anchors = html_to_text(body_html)
        if not body_text:
            body_text = visible
    rec.has_text_part = bool(payload.get("body_text"))

    for att in payload.get("attachments") or []:
        rec.attachments.append(
            Attachment(
                filename=str(att.get("filename") or "(unnamed)"),
                content_type=str(att.get("content_type") or ""),
                size_bytes=int(att.get("size_bytes") or 0),
            )
        )

    body = WS_RE.sub(" ", str(body_text)).strip()
    return _finalise(rec, body, build_links(anchors, body), warnings)
