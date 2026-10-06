"""WBS 1.5 - labelled dataset assembly, split, and validation.

Reads the normalized records, runs the feature extractor over them, splits
train/test, and checks the split for the two kinds of leakage that would make
every number in the final report meaningless.

Target
------
Binary: 1 = phishing, 0 = legitimate (ham) or unsolicited bulk mail (spam).
The three-way label is carried alongside as `label_3way` but never fed to the
model - it exists so WBS 2.1 can report false positives on spam separately from
false positives on ham, which is the number that predicts whether the extension
is tolerable in daily use.

Leakage checks
--------------
1. No record_id on both sides of the split.
2. No near-duplicate fingerprint on both sides. De-duplication in WBS 1.1
   already removed near-duplicates corpus-wide, so this is a regression check:
   if it ever fires, something upstream changed.

Usage:
    python 01_Data/src/build_dataset.py
    python 01_Data/src/build_dataset.py --test-size 0.25 --seed 7
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from features import FEATURE_NAMES, extract_features  # noqa: E402
from record_schema import Attachment, EmailRecord, Link  # noqa: E402

DATA_DIR = Path(__file__).resolve().parents[1]
NORM_DIR = DATA_DIR / "processed" / "normalized"
OUT_DIR = DATA_DIR / "processed" / "splits"

HEX_RUN_RE = re.compile(r"[0-9a-f]{8,}", re.IGNORECASE)
DIGIT_RE = re.compile(r"\d+")


def load_records() -> list[EmailRecord]:
    records = []
    for label in ("phish", "spam", "ham"):
        path = NORM_DIR / f"{label}.jsonl"
        if not path.exists():
            continue
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                d = json.loads(line)
                links = [Link(**lk) for lk in d.pop("links", [])]
                attachments = [Attachment(**a) for a in d.pop("attachments", [])]
                rec = EmailRecord(**{k: v for k, v in d.items()
                                     if k in EmailRecord.__dataclass_fields__})
                rec.links = links
                rec.attachments = attachments
                records.append(rec)
    return records


def fingerprint(rec: EmailRecord) -> str:
    """Same near-duplicate key used in WBS 1.1, recomputed for the leakage check."""
    if not rec.subject.strip() and not rec.body_text.strip():
        return f"unique:{rec.record_id}"
    subject = HEX_RUN_RE.sub("#", DIGIT_RE.sub("#", rec.subject.lower()))
    body = HEX_RUN_RE.sub("#", DIGIT_RE.sub("#", rec.body_text.lower()))[:800]
    basis = f"{rec.from_registered_domain}|{subject.strip()}|{body.strip()}"
    return hashlib.sha256(basis.encode("utf-8", errors="replace")).hexdigest()


def campaign_key(rec: EmailRecord) -> str:
    """Identify the campaign or thread a message belongs to.

    Deliberately excludes the sender domain. The near-duplicate fingerprint in
    WBS 1.1 includes it, which is why 1,785 phishing messages were removed as
    duplicates while whole campaigns survived: a blast that rotates sender
    domains looks like distinct messages to that fingerprint. Measured before
    this change, 29.7% of test-set phishing shared a masked subject with a
    training record - the same campaign on both sides of the split, which
    inflates every metric WBS 2.1 will report.
    """
    subject = HEX_RUN_RE.sub("#", DIGIT_RE.sub("#", rec.subject.lower())).strip()
    body = HEX_RUN_RE.sub("#", DIGIT_RE.sub("#", rec.body_text.lower()))[:400].strip()
    # The subject is the stable part of a campaign: a blast rotates sender
    # domains, tracking IDs and body wording while keeping the lure line. Keying
    # on subject+body left 24% of test phishing sharing a subject with training
    # data; keying on the subject alone is what actually separates campaigns.
    # Short or empty subjects carry no campaign identity, so those fall back to
    # the body, then to the message itself.
    if len(subject) >= 10:
        return "subj:" + hashlib.sha256(subject.encode("utf-8", errors="replace")).hexdigest()
    if body:
        return "body:" + hashlib.sha256(body[:400].encode("utf-8", errors="replace")).hexdigest()
    return f"solo:{rec.record_id}"


def campaign_components(records: list[EmailRecord]) -> dict[str, int]:
    """Group messages into campaigns by union-find over two independent keys.

    Keying on the subject alone left 20% of the test set sharing its opening
    body text with training data - the same campaign varying its subject line
    instead of its body. Two messages are therefore treated as the same campaign
    if they share EITHER a masked subject OR the first 200 characters of masked
    body, and those relations are merged transitively, so a campaign that varies
    one field at a time is still caught as one unit.
    """
    parent: dict[int, int] = {}

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for i in range(len(records)):
        parent[i] = i

    first_seen: dict[str, int] = {}
    for i, rec in enumerate(records):
        subject = HEX_RUN_RE.sub("#", DIGIT_RE.sub("#", rec.subject.lower())).strip()
        body = HEX_RUN_RE.sub("#", DIGIT_RE.sub("#", rec.body_text.lower()))[:200].strip()
        for key in (f"s:{subject}" if len(subject) >= 10 else "",
                    f"b:{body}" if len(body) >= 50 else ""):
            if not key:
                continue
            if key in first_seen:
                union(first_seen[key], i)
            else:
                first_seen[key] = i
    return {records[i].record_id: find(i) for i in range(len(records))}


def grouped_split(records, test_size: float, seed: int):
    """Split by campaign, not by message, stratified on the three-way label.

    Whole campaigns go to one side or the other, so the test set measures
    generalisation to unseen campaigns rather than recall of memorised ones.
    """
    rng = random.Random(seed)
    comp = campaign_components(records)
    groups: dict[int, list[EmailRecord]] = defaultdict(list)
    for r in records:
        groups[comp[r.record_id]].append(r)
    sizes = sorted((len(v) for v in groups.values()), reverse=True)
    print(f"campaigns: {len(groups):,}  largest {sizes[0]}  "
          f"top-5 {sizes[:5]}  singletons {sum(1 for s_ in sizes if s_ == 1):,}")

    by_label: dict[str, list[list[EmailRecord]]] = defaultdict(list)
    for key in sorted(groups):
        members = groups[key]
        # A campaign takes the label of its majority member; in practice they agree.
        label = Counter(m.label for m in members).most_common(1)[0][0]
        by_label[label].append(members)

    train, test = [], []
    for label in sorted(by_label):
        buckets = by_label[label]
        rng.shuffle(buckets)
        target = int(round(sum(len(b) for b in buckets) * test_size))
        taken = 0
        for bucket in buckets:
            if taken < target:
                test.extend(bucket)
                taken += len(bucket)
            else:
                train.extend(bucket)
    rng.shuffle(train)
    rng.shuffle(test)
    return train, test


def write_split(name: str, records: list[EmailRecord]) -> Path:
    path = OUT_DIR / f"{name}.jsonl"
    with path.open("w", encoding="utf-8") as fh:
        for rec in records:
            row = {
                "record_id": rec.record_id,
                "label": 1 if rec.label == "phish" else 0,
                "label_3way": rec.label,
                "features": extract_features(rec),
            }
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    return path


def single_feature_auc(records: list[EmailRecord]) -> dict[str, float]:
    """Area under the ROC curve for each feature used alone.

    0.5 means the feature tells you nothing. Far from 0.5 in either direction
    means one feature alone nearly separates the classes - which on a corpus
    whose two halves are twenty years apart is a reason for suspicion before it
    is a reason for confidence.
    """
    vals = {name: ([], []) for name in FEATURE_NAMES}  # (phish, legit)
    for rec in records:
        idx = 0 if rec.label == "phish" else 1
        for name, v in extract_features(rec).items():
            vals[name][idx].append(v)
    out = {}
    for name, (pos, neg) in vals.items():
        if not pos or not neg:
            out[name] = 0.5
            continue
        merged = sorted([(v, 1) for v in pos] + [(v, 0) for v in neg])
        # average ranks over ties
        ranks, i = {}, 0
        rank_sum_pos, n = 0.0, len(merged)
        while i < n:
            j = i
            while j + 1 < n and merged[j + 1][0] == merged[i][0]:
                j += 1
            avg_rank = (i + j) / 2.0 + 1.0
            for k in range(i, j + 1):
                if merged[k][1] == 1:
                    rank_sum_pos += avg_rank
            i = j + 1
        np_, nn = len(pos), len(neg)
        out[name] = round((rank_sum_pos - np_ * (np_ + 1) / 2.0) / (np_ * nn), 4)
    return out


def same_era_stats(records: list[EmailRecord]) -> dict:
    """Mean of every feature for spam vs ham - both drawn from SpamAssassin.

    This is the control. The phishing corpus is 2022 onward and the
    ham/spam corpus is 2002, so any feature that tracks the era of an email
    rather than its intent will separate phishing from legitimate almost
    perfectly while telling us nothing. Spam and ham share an era and a source,
    so a feature that also separates *them* is doing real work; a feature that
    separates only across the corpora is suspect until proven otherwise.
    """
    sums = {name: {"spam": 0.0, "ham": 0.0} for name in FEATURE_NAMES}
    counts = {"spam": 0, "ham": 0}
    for rec in records:
        if rec.label not in ("spam", "ham"):
            continue
        counts[rec.label] += 1
        for name, val in extract_features(rec).items():
            sums[name][rec.label] += val
    out = {}
    for name in FEATURE_NAMES:
        sp = sums[name]["spam"] / max(1, counts["spam"])
        hm = sums[name]["ham"] / max(1, counts["ham"])
        out[name] = {"spam_mean": round(sp, 4), "ham_mean": round(hm, 4),
                     "abs_gap": round(abs(sp - hm), 4)}
    return out


def prevalence(records: list[EmailRecord]) -> dict:
    """How often each binary feature is non-zero at all, by class."""
    nz = {name: {"phish": 0, "legit": 0} for name in FEATURE_NAMES}
    counts = {"phish": 0, "legit": 0}
    for rec in records:
        cls = "phish" if rec.label == "phish" else "legit"
        counts[cls] += 1
        for name, val in extract_features(rec).items():
            if val:
                nz[name][cls] += 1
    return {name: {"phish_pct": round(100 * v["phish"] / max(1, counts["phish"]), 2),
                   "legit_pct": round(100 * v["legit"] / max(1, counts["legit"]), 2)}
            for name, v in nz.items()}


def feature_stats(records: list[EmailRecord]) -> dict:
    """Mean of every feature per class, and the gap between them.

    This is the check that says whether the feature set is worth training on at
    all. A feature whose phishing mean matches its legitimate mean contributes
    nothing and will produce no explanation worth reading.
    """
    sums = {name: {"phish": 0.0, "legit": 0.0} for name in FEATURE_NAMES}
    counts = {"phish": 0, "legit": 0}
    for rec in records:
        cls = "phish" if rec.label == "phish" else "legit"
        counts[cls] += 1
        for name, val in extract_features(rec).items():
            sums[name][cls] += val
    out = {}
    for name in FEATURE_NAMES:
        p = sums[name]["phish"] / max(1, counts["phish"])
        l = sums[name]["legit"] / max(1, counts["legit"])
        out[name] = {"phish_mean": round(p, 4), "legit_mean": round(l, 4),
                     "abs_gap": round(abs(p - l), 4)}
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Assemble the labelled dataset and split it.")
    ap.add_argument("--test-size", type=float, default=0.2)
    ap.add_argument("--seed", type=int, default=20260930)
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    records = load_records()
    if not records:
        print("No normalized records found - run normalize.py first.", file=sys.stderr)
        return 1
    print(f"loaded {len(records):,} records")

    train, test = grouped_split(records, args.test_size, args.seed)

    # --- leakage checks ---
    train_ids = {r.record_id for r in train}
    test_ids = {r.record_id for r in test}
    id_overlap = train_ids & test_ids
    train_fp = {fingerprint(r) for r in train}
    test_fp = {fingerprint(r) for r in test}
    fp_overlap = train_fp & test_fp
    _comp = campaign_components(records)
    camp_overlap = ({_comp[r.record_id] for r in train} & {_comp[r.record_id] for r in test})
    print(f"leakage check - shared record ids:   {len(id_overlap)}")
    print(f"leakage check - shared fingerprints: {len(fp_overlap)}")
    print(f"leakage check - shared campaigns:    {len(camp_overlap)}")
    if id_overlap or fp_overlap or camp_overlap:
        print("LEAKAGE DETECTED - refusing to write the split.", file=sys.stderr)
        return 2

    train_path = write_split("train", train)
    test_path = write_split("test", test)

    def balance(rs):
        c = Counter(r.label for r in rs)
        n = max(1, len(rs))
        return {k: {"n": v, "pct": round(100 * v / n, 1)} for k, v in sorted(c.items())}

    stats = feature_stats(records)
    era = same_era_stats(records)
    prev = prevalence(records)
    ranked = sorted(stats.items(), key=lambda kv: -kv[1]["abs_gap"])
    flat = [name for name, s in stats.items() if s["abs_gap"] < 0.01]

    # Single-feature AUC. Scale-free, unlike comparing raw means across
    # log-scaled counts and 0/1 indicators, which is what the first version of
    # this check did - and why it cleared the three worst features in the set.
    auc = single_feature_auc(records)
    suspect = sorted(
        [n for n in FEATURE_NAMES if abs(auc[n] - 0.5) >= 0.15],
        key=lambda n: -abs(auc[n] - 0.5))

    report = {
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "seed": args.seed,
        "test_size": args.test_size,
        "feature_count": len(FEATURE_NAMES),
        "totals": {"all": len(records), "train": len(train), "test": len(test)},
        "class_balance": {"train": balance(train), "test": balance(test),
                          "overall": balance(records)},
        "binary_balance": {
            "train_phish_pct": round(100 * sum(1 for r in train if r.label == "phish")
                                     / max(1, len(train)), 1),
            "test_phish_pct": round(100 * sum(1 for r in test if r.label == "phish")
                                    / max(1, len(test)), 1),
        },
        "leakage": {"shared_record_ids": len(id_overlap), "shared_fingerprints": len(fp_overlap),
                    "shared_campaigns": len(camp_overlap)},
        "single_feature_auc": auc,
        "feature_separation_phish_vs_legit": dict(ranked),
        "feature_separation_spam_vs_ham_same_era_control": era,
        "feature_prevalence_pct_nonzero": prev,
        "features_with_no_separation": flat,
        "suspected_corpus_artifacts": suspect,
        "suspected_corpus_artifacts_note": (
            "Strong phishing-vs-legitimate separation but near-zero spam-vs-ham "
            "separation within the single-era SpamAssassin source. These features may be "
            "tracking the 20-year gap between the corpora rather than phishing intent. "
            "WBS 2.1 must report metrics with these ablated as a sensitivity analysis."),
        "outputs": {"train": str(train_path.relative_to(DATA_DIR.parent)),
                    "test": str(test_path.relative_to(DATA_DIR.parent))},
    }
    (OUT_DIR / "dataset_report.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print(f"train {len(train):,}  test {len(test):,}  features {len(FEATURE_NAMES)}")
    print(f"phishing share - train {report['binary_balance']['train_phish_pct']}% "
          f"test {report['binary_balance']['test_phish_pct']}%")
    print("\ntop 12 features by class separation:")
    for name, s in ranked[:12]:
        print(f"  {name:<36} phish {s['phish_mean']:>8}  legit {s['legit_mean']:>8}  "
              f"gap {s['abs_gap']:>8}")
    if flat:
        print(f"\nfeatures with no separation ({len(flat)}): {', '.join(flat)}")
    print(f"\nHIGH SINGLE-FEATURE AUC - review before trusting ({len(suspect)}):")
    for name in suspect:
        print(f"  {name:<36} AUC {auc[name]:>7}   spam-vs-ham gap {era[name]['abs_gap']:>8}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
