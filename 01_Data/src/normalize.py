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
import hashlib
import json
import os
import re
import sys
import tarfile
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from record_schema import SCHEMA_VERSION, EmailRecord  # noqa: E402

DATA_DIR = Path(__file__).resolve().parents[1]
RAW_DIR = Path(os.environ.get("PHISHLENS_RAW_DIR") or DATA_DIR / "raw")
OUT_DIR = DATA_DIR / "processed" / "normalized"

# The parser lives in parse_email.py (WBS 1.3). normalize.py imports it rather
# than carrying a second copy, so corpus records and live Gmail records can never
# drift apart.
from parse_email import parse_raw_message  # noqa: E402

HEX_RUN_RE = re.compile(r"[0-9a-f]{8,}", re.IGNORECASE)
DIGIT_RE = re.compile(r"\d+")


def parse_message(raw: bytes, source: str, group: str, path: str, label: str) -> EmailRecord:
    """Thin wrapper kept so existing callers and tests keep working."""
    return parse_raw_message(raw, source, group, path, label)


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


def read_personal_ham(limit: int | None):
    """Stream legitimate mail out of a personal mbox export (WBS 1.6).

    Why this reader exists
    ----------------------
    The legitimate half of the corpus was the 2002 SpamAssassin collection while
    the phishing half is 2022+, and WBS 2.4 proved the model was exploiting that
    twenty-year gap rather than detecting phishing. The clearest case is
    `has_http_only_link`: 80% of the 2002 legitimate mail carries a plain http
    link against 37% of the phishing, so the model learned "http link means
    safe" - and modern mail, which is https throughout, is therefore scored as
    unsafe. Rescoring the same 818 legitimate test messages with that one
    feature flipped to https raises their caution rate from 11.9% to 59.2%.
    Modern legitimate mail is the only thing that fixes that measurement.

    Privacy
    -------
    The mbox is read from 01_Data/raw/, which is gitignored, and nothing derived
    from it carries message content any further: the split files hold a record
    id, a label and 43 numbers. The messages themselves never leave the machine
    this runs on. See 00_Admin/data-handling.md.

    Labelling
    ---------
    Everything here is labelled ham. That is an assumption, not a fact - it
    holds only if the export excludes Spam and Trash, which is what the
    instructions in CORPUS.md say to do. A phishing message that reached the
    inbox and got exported would be mislabelled, and at this corpus size a
    handful of those would matter, so the export is a filtered label rather than
    "all mail".
    """
    path = Path(os.environ.get("PHISHLENS_HAM_MBOX") or RAW_DIR / "personal_ham.mbox")
    if not path.exists():
        return
    count = 0
    # Streamed by hand rather than via the mailbox module: mailbox.mbox builds
    # an index of the whole file up front, which is slow and memory-hungry on a
    # multi-gigabyte Takeout export.
    buf: list[bytes] = []
    with path.open("rb") as fh:
        for line in fh:
            if line.startswith(b"From ") and buf:
                raw = b"".join(buf)
                buf = [line]
                if limit is not None and count >= limit:
                    return
                count += 1
                yield raw, "personal", "inbox", f"{path.name}:{count}", "ham"
                continue
            buf.append(line)
    if buf and (limit is None or count < limit):
        yield b"".join(buf), "personal", "inbox", f"{path.name}:{count + 1}", "ham"


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
        choices=("phishing_pot", "spamassassin", "personal_ham"),
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

    # personal_ham is opt-in: it is only present on a machine that has the
    # author's own mail export, so a default run must not require it.
    archives = [RAW_DIR / n for n in ("phishing_pot.tar.gz", "spamassassin.tar.gz")
                if n.split(".")[0].replace("_tar", "") in
                {"phishing_pot", "spamassassin"} & selected]
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
        if "personal_ham" in selected:
            readers.append(read_personal_ham(args.limit))
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
        "generated_utc": datetime.now(UTC).isoformat(timespec="seconds"),
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
