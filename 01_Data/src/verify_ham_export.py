"""Verify a Google Takeout mbox before it enters the corpus. WBS 1.6.

    python 01_Data/src/verify_ham_export.py 01_Data/raw/personal_ham.mbox

Prints aggregate counts only -- no subjects, no addresses, no body text. The
corpus documentation promises that this mail never leaves the machine, so a
check on it has to be safe to read aloud and safe to paste into a chat window.
Nothing here writes a file or sends anything anywhere.

What it checks, and why each one matters:

1. Message count. Has to be large enough to be worth having. Under about 500
   messages the legitimate class is too small to rebalance against 6,820
   phishing samples.

2. Gmail labels. A Takeout export carries X-Gmail-Labels on each message. Every
   message here is labelled `ham` by assumption, and that assumption holds only
   if Spam and Trash were excluded at export time. This is the one check that
   can invalidate the whole corpus, and it is invisible without looking.

3. Date range. The entire point of WBS 1.6 is modern mail. If a third of the
   export is from 2014 the vintage gap is narrowed rather than closed.

4. Link scheme. The hypothesis is that the model learned `plain http link means
   safe` from a 2002 corpus where 80% of legitimate mail carried one, against
   37% of the phishing. Modern mail should be overwhelmingly https. If this
   export is not, the diagnosis is wrong and 2.4 needs rethinking before any
   retraining happens.
"""

from __future__ import annotations

import re
import sys
from collections import Counter
from datetime import datetime
from email.utils import parsedate_to_datetime
from pathlib import Path

LABELS_RE = re.compile(rb"^X-Gmail-Labels:\s*(.*)$", re.IGNORECASE)
DATE_RE = re.compile(rb"^Date:\s*(.*)$", re.IGNORECASE)
HTTP_RE = re.compile(rb"http://[^\s\"'<>)]+", re.IGNORECASE)
HTTPS_RE = re.compile(rb"https://[^\s\"'<>)]+", re.IGNORECASE)

# Labels that mean the message should not be in a corpus labelled "legitimate".
SUSPECT_LABELS = {"spam", "trash"}


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__.strip().splitlines()[2].strip())
        return 2

    path = Path(argv[1])
    if not path.exists():
        print(f"NOT FOUND: {path}")
        return 1

    size = path.stat().st_size
    print(f"File:  {path}")
    print(f"Size:  {size / (1024*1024):.1f} MB")
    print()

    messages = 0
    labels = Counter()
    suspect_messages = 0
    years = Counter()
    undated = 0
    with_https = 0
    with_http_only = 0
    with_no_link = 0

    def finish(buf: list[bytes]) -> None:
        nonlocal messages, suspect_messages, undated, with_https, with_http_only, with_no_link
        if not buf:
            return
        messages += 1
        raw = b"".join(buf)

        # Headers end at the first blank line.
        split = raw.find(b"\n\n")
        head = raw[:split] if split != -1 else raw

        seen_suspect = False
        for line in head.split(b"\n"):
            m = LABELS_RE.match(line)
            if m:
                for lab in m.group(1).decode("utf-8", "replace").split(","):
                    lab = lab.strip()
                    if not lab:
                        continue
                    labels[lab] += 1
                    if lab.lower() in SUSPECT_LABELS:
                        seen_suspect = True
                continue
            d = DATE_RE.match(line)
            if d:
                try:
                    dt = parsedate_to_datetime(d.group(1).decode("utf-8", "replace"))
                    years[dt.year] += 1
                except Exception:
                    undated += 1
        if seen_suspect:
            suspect_messages += 1

        has_https = bool(HTTPS_RE.search(raw))
        has_http = bool(HTTP_RE.search(raw))
        if has_https:
            with_https += 1
        elif has_http:
            with_http_only += 1
        else:
            with_no_link += 1

    buf: list[bytes] = []
    with path.open("rb") as fh:
        for line in fh:
            if line.startswith(b"From ") and buf:
                finish(buf)
                buf = [line]
                continue
            buf.append(line)
    finish(buf)

    if messages == 0:
        print("NO MESSAGES FOUND. This does not look like an mbox file.")
        return 1

    print(f"Messages: {messages:,}")
    if messages < 500:
        print("  WARNING: under 500 messages is thin for a training class.")
    print()

    print("Gmail labels (top 12):")
    if not labels:
        print("  none found -- this may not be a Takeout export, so the")
        print("  Spam/Trash check below could not run. Verify by hand.")
    else:
        for lab, n in labels.most_common(12):
            flag = "  <-- MUST NOT BE HERE" if lab.lower() in SUSPECT_LABELS else ""
            print(f"  {lab:<28} {n:>7,}{flag}")
    print()
    if suspect_messages:
        print(f"  FAIL: {suspect_messages:,} messages carry a Spam or Trash label.")
        print("  Re-export with those deselected. Every message here is assumed")
        print("  legitimate, and a phish in the pile is a mislabelled sample.")
    else:
        print("  PASS: no Spam or Trash labelled messages.")
    print()

    print("Messages by year:")
    recent = 0
    for year in sorted(years):
        n = years[year]
        bar = "#" * max(1, round(40 * n / max(years.values())))
        print(f"  {year}  {n:>7,}  {bar}")
        if year >= 2020:
            recent += n
    if undated:
        print(f"  (unparsable Date header: {undated:,})")
    dated = sum(years.values())
    if dated:
        pct = 100 * recent / dated
        print(f"\n  {pct:.1f}% of dated messages are 2020 or later.")
        if pct < 80:
            print("  WARNING: a large share is older than intended. WBS 1.6 is")
            print("  about closing a vintage gap, not narrowing it.")
    print()

    print("Link scheme (the hypothesis check):")
    print(f"  any https link      {with_https:>7,}  ({100*with_https/messages:.1f}%)")
    print(f"  http links only     {with_http_only:>7,}  ({100*with_http_only/messages:.1f}%)")
    print(f"  no links at all     {with_no_link:>7,}  ({100*with_no_link/messages:.1f}%)")
    print()
    print("  For reference, the 2002 SpamAssassin legitimate corpus carries a")
    print("  plain http link in 80% of messages, against 37% of the phishing.")
    linked = with_https + with_http_only
    if linked:
        http_only_pct = 100 * with_http_only / linked
        print(f"  This export: {http_only_pct:.1f}% of messages with links are http-only.")
        if http_only_pct > 40:
            print("  UNEXPECTED: that is close to the old corpus. Check the")
            print("  diagnosis in CORPUS.md before retraining on this.")
        else:
            print("  Consistent with the diagnosis: modern mail is https.")

    print()
    print(f"Checked {messages:,} messages at {datetime.now():%Y-%m-%d %H:%M}.")
    print("No message content was printed, written, or transmitted.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
