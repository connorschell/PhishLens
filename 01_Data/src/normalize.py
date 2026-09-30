"""WBS 1.1 - normalization and de-duplication.

Reads every message in 01_Data/raw/ and writes 01_Data/processed/normalized/
as JSON Lines in the common record schema, one file per label, plus a report.

De-duplication happens in two passes:
  1. Exact:  identical raw bytes (the same message mirrored twice).
  2. Near:   identical normalized fingerprint - lowercased sender domain, subject
             with digits and long hex runs masked, and the first 800 characters
             of whitespace-collapsed body text. This is what catches a phishing
             campaign blasted from one template with a rotating tracking ID,
             which would otherwise leak between train and test and flatter the
             model.

Usage
-----
    python 01_Data/src/normalize.py
    python 01_Data/src/normalize.py --limit 200      # quick smoke run
"""

from __future__ import annotations

import argparse
import email
import email.policy
import hashlib
import json
import os
import re
import sys
import tarfile
from collections import Counter
from datetime import datetime, timezone
from email.header import decode_header, make_header
from email.utils import parsedate_to_datetime, parseaddr
from pathlib import Path

from bs4 import BeautifulSoup

try:
    import tldextract

    _EXTRACT = tldextract.TLDExtract(suffix_list_urls=())  # offline: bundled snapshot
except Exception:  # pragma: no cover - tldextract is in requirements.txt
    _EXTRACT = None

sys.path.insert(0, str(Path(__file__).resolve().parent))
from record_schema import SCHEMA_VERSION, Attachment, EmailRecord, Link  # noqa: E402

DATA_DIR = Path(__file__).resolve().parents[1]
RAW_DIR = Path(os.environ.get("PHISHLENS_RAW_DIR") or DATA_DIR / "raw")
OUT_DIR = DATA_DIR / "processed" / "normalized"

URL_RE = re.compile(r"""https?://[^\s<>"'\])}]+""", re.IGNORECASE)
HEX_RUN_RE = re.compile(r"[0-9a-f]{8,}", re.IGNORECASE)
DIGIT_RE = re.compile(r"\d+")
WS_RE = re.compile(r"\s+")


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def decode_hdr(value: object | None) -> str:
    """Decode RFC 2047 encoded-words; fall back to the raw string.

    Values arriving from email.message can be str or email.header.Header, and
    malformed corpus messages produce both, so everything is coerced to str first.
    """
    if not value:
        return ""
    value = str(value)
    try:
        return str(make_header(decode_header(value))).strip()
    except Exception:
        return str(value).strip()


def registered_domain(host: str) -> str:
    if not host:
        return ""
    host = host.strip().strip(".").lower()
    if _EXTRACT is not None:
        parts = _EXTRACT(host)
        if parts.domain and parts.suffix:
            return f"{parts.domain}.{parts.suffix}"
        return parts.domain or host
    bits = host.split(".")
    return ".".join(bits[-2:]) if len(bits) >= 2 else host


def host_of(url: str) -> str:
    m = re.match(r"^\s*([a-z][a-z0-9+.-]*)://([^/?#\s]+)", url, re.IGNORECASE)
    if not m:
        return ""
    netloc = m.group(2)
    netloc = netloc.split("@")[-1]  # strip userinfo, a classic obfuscation
    return netloc.split(":")[0].lower()


def scheme_of(url: str) -> str:
    m = re.match(r"^\s*([a-z][a-z0-9+.-]*)://", url, re.IGNORECASE)
    return m.group(1).lower() if m else ""


def domain_of_address(addr: str) -> str:
    return addr.split("@")[-1].strip().lower() if "@" in addr else ""


def html_to_text(html: str) -> tuple[str, list[tuple[str, str]]]:
    """Return (visible text, [(href, anchor text)])."""
    try:
        soup = BeautifulSoup(html, "lxml")  # ~3x faster than html.parser on real mail
    except Exception:
        soup = BeautifulSoup(html, "html.parser")
    anchors = []
    for a in soup.find_all("a"):
        href = (a.get("href") or "").strip()
        if href:
            anchors.append((href, a.get_text(" ", strip=True)))
    for tag in soup(["script", "style", "head"]):
        tag.decompose()
    return soup.get_text(" ", strip=True), anchors


# --------------------------------------------------------------------------- #
# parsing
# --------------------------------------------------------------------------- #
def parse_message(raw: bytes, source: str, group: str, path: str, label: str) -> EmailRecord:
    warnings: list[str] = []
    try:
        msg = email.message_from_bytes(raw, policy=email.policy.compat32)
    except Exception as exc:
        warnings.append(f"parse_failed:{type(exc).__name__}")
        msg = email.message_from_string("", policy=email.policy.compat32)

    rec = EmailRecord(
        record_id=hashlib.sha256(raw).hexdigest()[:24],
        source_corpus=source,
        source_group=group,
        source_path=path,
        label=label,
        schema_version=SCHEMA_VERSION,
    )

    # --- sender and envelope ---
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

    competing = {
        registered_domain(d)
        for d in (rec.reply_to_domain, domain_of_address(rec.return_path_address))
        if d
    }
    rec.sender_mismatch = bool(
        rec.from_registered_domain and competing and rec.from_registered_domain not in competing
    )

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

    # --- body and attachments ---
    text_parts: list[str] = []
    html_parts: list[str] = []
    for part in msg.walk():
        if part.is_multipart():
            continue
        ctype = (part.get_content_type() or "").lower()
        disposition = str(part.get("Content-Disposition") or "").lower()
        filename = decode_hdr(part.get_filename())

        if filename or "attachment" in disposition:
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
            text = payload.decode(charset, errors="replace")
        except (LookupError, UnicodeDecodeError):
            text = payload.decode("utf-8", errors="replace")
            # Malformed messages put whole HTML documents in the charset parameter,
            # so the label is clipped before it becomes a report key.
            label = re.sub(r"[^A-Za-z0-9_.:-]", "", str(charset))[:24] or "unknown"
            warnings.append(f"charset_fallback:{label}")

        if ctype == "text/plain":
            text_parts.append(text)
        elif ctype == "text/html":
            html_parts.append(text)

    rec.has_text_part = bool(text_parts)
    rec.has_html_part = bool(html_parts)

    anchors: list[tuple[str, str]] = []
    if html_parts:
        for html in html_parts:
            visible, found = html_to_text(html)
            anchors.extend(found)
            if not text_parts:
                text_parts.append(visible)

    body = WS_RE.sub(" ", "\n".join(text_parts)).strip()
    rec.body_text = body
    rec.body_char_count = len(body)
    rec.body_word_count = len(body.split())
    if not body and not rec.attachments:
        warnings.append("empty_body")

    # --- links: anchors first, then bare URLs in the text ---
    seen: set[str] = set()
    for href, anchor_text in anchors:
        if not href.lower().startswith(("http://", "https://")):
            continue
        host = host_of(href)
        reg = registered_domain(host)
        anchor_domains = {registered_domain(host_of(u)) for u in URL_RE.findall(anchor_text)}
        anchor_domains.discard("")
        mismatch = bool(anchor_domains and reg and reg not in anchor_domains)
        rec.links.append(
            Link(
                url=href[:2048],
                host=host,
                registered_domain=reg,
                scheme=scheme_of(href),
                display_text=anchor_text[:200],
                in_html=True,
                display_mismatch=mismatch,
            )
        )
        seen.add(href)

    for url in URL_RE.findall(body):
        url = url.rstrip(".,;:!?")
        if url in seen:
            continue
        seen.add(url)
        host = host_of(url)
        rec.links.append(
            Link(
                url=url[:2048],
                host=host,
                registered_domain=registered_domain(host),
                scheme=scheme_of(url),
                in_html=False,
            )
        )

    rec.link_count = len(rec.links)
    rec.distinct_link_domains = len({lk.registered_domain for lk in rec.links if lk.registered_domain})
    rec.display_mismatch_count = sum(1 for lk in rec.links if lk.display_mismatch)
    rec.attachment_count = len(rec.attachments)
    rec.parse_warnings = sorted(set(warnings))
    return rec


# --------------------------------------------------------------------------- #
# de-duplication
# --------------------------------------------------------------------------- #
def fingerprint(rec: EmailRecord) -> str:
    """Return the near-duplicate key, or a unique key when there is nothing to compare.

    A message with neither subject nor body text carries no campaign signal, so
    fingerprinting it would silently collapse every unparsable message into one.
    Those fall back to their own record id and survive de-duplication.
    """
    if not rec.subject.strip() and not rec.body_text.strip():
        return f"unique:{rec.record_id}"
    subject = HEX_RUN_RE.sub("#", DIGIT_RE.sub("#", rec.subject.lower()))
    body = HEX_RUN_RE.sub("#", DIGIT_RE.sub("#", rec.body_text.lower()))[:800]
    basis = f"{rec.from_registered_domain}|{subject.strip()}|{body.strip()}"
    return hashlib.sha256(basis.encode("utf-8", errors="replace")).hexdigest()


# --------------------------------------------------------------------------- #
# corpus readers
# --------------------------------------------------------------------------- #
def read_spamassassin(limit: int | None):
    """Stream messages out of raw/spamassassin.tar.gz.

    Members are <group>/<id>.json, e.g. easy-ham-1/00001.json. Anything not in a
    group directory (the corpus index files) is skipped. Groups whose name starts
    with "spam" are unsolicited bulk mail; everything else is legitimate mail.
    """
    archive = RAW_DIR / "spamassassin.tar.gz"
    if not archive.exists():
        return
    count = 0
    with tarfile.open(archive, "r:gz") as tar:
        for member in tar:
            if not member.isfile() or not member.name.endswith(".json"):
                continue
            parts = member.name.split("/")
            if len(parts) != 2:
                continue
            group = parts[0]
            if limit is not None and count >= limit:
                return
            fh = tar.extractfile(member)
            if fh is None:
                continue
            try:
                payload = json.loads(fh.read().decode("utf-8", errors="replace"))
            except Exception:
                continue
            raw = (payload.get("text") or "").encode("utf-8", errors="replace")
            if not raw:
                continue
            count += 1
            label = "spam" if group.startswith("spam") else "ham"
            yield raw, "spamassassin", group, f"spamassassin.tar.gz:{member.name}", label


def read_phishing_pot(limit: int | None):
    """Stream .eml messages out of raw/phishing_pot.tar.gz."""
    archive = RAW_DIR / "phishing_pot.tar.gz"
    if not archive.exists():
        return
    count = 0
    with tarfile.open(archive, "r:gz") as tar:
        for member in tar:
            if not member.isfile() or not member.name.endswith(".eml"):
                continue
            if limit is not None and count >= limit:
                return
            fh = tar.extractfile(member)
            if fh is None:
                continue
            raw = fh.read()
            if not raw:
                continue
            count += 1
            yield raw, "phishing_pot", "email", f"phishing_pot.tar.gz:{member.name}", "phish"


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def main() -> int:
    parser = argparse.ArgumentParser(description="Normalize and de-duplicate the corpora.")
    parser.add_argument("--limit", type=int, default=None, help="max messages per corpus")
    parser.add_argument(
        "--only",
        choices=("phishing_pot", "spamassassin"),
        action="append",
        help="process just this corpus; repeatable. Use with --append to build the "
             "output across several runs on a machine with a short job limit.",
    )
    parser.add_argument(
        "--append",
        action="store_true",
        help="add to the existing output files and reuse the saved de-duplication "
             "state, instead of starting fresh",
    )
    args = parser.parse_args()
    selected = set(args.only) if args.only else {"phishing_pot", "spamassassin"}

    archives = [RAW_DIR / "phishing_pot.tar.gz", RAW_DIR / "spamassassin.tar.gz"]
    missing = [a.name for a in archives if not a.exists()]
    if missing:
        print(f"missing in {RAW_DIR}: {', '.join(missing)} - run acquire_corpus.py first.",
              file=sys.stderr)
        return 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    mode = "a" if args.append else "w"
    handles = {label: (OUT_DIR / f"{label}.jsonl").open(mode, encoding="utf-8") for label in
               ("phish", "spam", "ham")}

    # De-duplication has to see every message, but the corpora may be processed in
    # separate runs, so the hashes are persisted between them.
    state_path = OUT_DIR / ".dedup_state.json"
    seen_raw: set[str] = set()
    seen_fp: dict[str, str] = {}
    prior_counts: dict[str, dict[str, int]] = {}
    if args.append and state_path.exists():
        state = json.loads(state_path.read_text(encoding="utf-8"))
        seen_raw = set(state.get("seen_raw", []))
        seen_fp = dict.fromkeys(state.get("seen_fp", []), "")
        prior_counts = state.get("counts", {})
        print(f"resuming with {len(seen_raw):,} known messages")
    stats = {
        "read": Counter(),
        "kept": Counter(),
        "dup_exact": Counter(),
        "dup_near": Counter(),
        "warnings": Counter(),
    }
    link_totals = Counter()

    try:
        readers = []
        if "phishing_pot" in selected:
            readers.append(read_phishing_pot(args.limit))
        if "spamassassin" in selected:
            readers.append(read_spamassassin(args.limit))
        for reader in readers:
            for raw, source, group, path, label in reader:
                stats["read"][label] += 1
                raw_hash = hashlib.sha256(raw).hexdigest()
                if raw_hash in seen_raw:
                    stats["dup_exact"][label] += 1
                    continue
                seen_raw.add(raw_hash)

                rec = parse_message(raw, source, group, path, label)
                fp = fingerprint(rec)
                if fp in seen_fp:
                    stats["dup_near"][label] += 1
                    continue
                seen_fp[fp] = rec.record_id

                for w in rec.parse_warnings:
                    stats["warnings"][w] += 1
                link_totals[label] += rec.link_count
                handles[label].write(json.dumps(rec.to_json_dict(), ensure_ascii=False) + "\n")
                stats["kept"][label] += 1
    finally:
        for fh in handles.values():
            fh.close()

    def merged(key: str, counter: Counter) -> dict[str, int]:
        out = dict(prior_counts.get(key, {}))
        for label, n in counter.items():
            out[label] = out.get(label, 0) + n
        return out

    counts_now = {
        "messages_read": merged("messages_read", stats["read"]),
        "messages_kept": merged("messages_kept", stats["kept"]),
        "removed_exact_duplicates": merged("removed_exact_duplicates", stats["dup_exact"]),
        "removed_near_duplicates": merged("removed_near_duplicates", stats["dup_near"]),
        "parse_warnings": merged("parse_warnings", stats["warnings"]),
        "link_totals": merged("link_totals", link_totals),
    }
    state_path.write_text(
        json.dumps(
            {"seen_raw": sorted(seen_raw), "seen_fp": sorted(seen_fp), "counts": counts_now},
            indent=0,
        ),
        encoding="utf-8",
    )

    report = {
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "schema_version": SCHEMA_VERSION,
        "corpora_processed": sorted(selected),
        "messages_read": counts_now["messages_read"],
        "messages_kept": counts_now["messages_kept"],
        "removed_exact_duplicates": counts_now["removed_exact_duplicates"],
        "removed_near_duplicates": counts_now["removed_near_duplicates"],
        "mean_links_per_message": {
            label: round(counts_now["link_totals"][label] / kept, 2)
            for label, kept in counts_now["messages_kept"].items()
            if kept
        },
        "parse_warnings": counts_now["parse_warnings"],
        "outputs": {label: f"01_Data/processed/normalized/{label}.jsonl" for label in handles},
    }
    (OUT_DIR / "normalization_report.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )

    print(f"read {sum(counts_now['messages_read'].values()):,} messages, "
          f"kept {sum(counts_now['messages_kept'].values()):,} (cumulative)")
    for label in ("phish", "spam", "ham"):
        print(
            f"  {label:<6} read {counts_now['messages_read'].get(label, 0):>6,}"
            f"  kept {counts_now['messages_kept'].get(label, 0):>6,}"
            f"  exact-dup {counts_now['removed_exact_duplicates'].get(label, 0):>5,}"
            f"  near-dup {counts_now['removed_near_duplicates'].get(label, 0):>5,}"
        )
    print(f"Report written to {OUT_DIR / 'normalization_report.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
