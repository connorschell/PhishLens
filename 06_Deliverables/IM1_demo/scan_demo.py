"""IM1 demo - end-to-end scan over held-out messages, rendered as the panel.

Runs the real chain, in the order the extension will run it:

    normalized message -> features.extract_features  (WBS 1.4)
                       -> contributions.score_features (WBS 2.2)
                       -> explain.explain             (WBS 2.3)
                       -> panel HTML                  (preview of WBS 4.3)

Nothing in the output is written by hand. Every score, tier, and sentence on
the page is produced by the code above from a message in the held-out test
split, which the model never saw during training.

The four messages are selected by rule, not picked by eye:

    1. the highest-scoring phishing message that also trips a deterministic
       rule, so both explanation layers appear
    2. the legitimate message the model was most confident about
    3. the least confident phishing message still flagged at all - the one
       that shows what a borderline verdict looks like
    4. the legitimate message that scored highest - the worst false positive
       in the test set, included because a demo that only shows wins is not
       evidence of anything

Usage:
    python 06_Deliverables/IM1_demo/scan_demo.py
"""

from __future__ import annotations

import html
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "01_Data" / "src"))
sys.path.insert(0, str(ROOT / "02_Model"))

from record_schema import Attachment, EmailRecord, Link  # noqa: E402
from contributions import load_bundle  # noqa: E402
from explain import explain  # noqa: E402

SPLITS = ROOT / "01_Data" / "processed" / "splits"
NORM = ROOT / "01_Data" / "processed" / "normalized"
OUT = Path(__file__).resolve().parent


def load_records() -> dict[str, EmailRecord]:
    by_id = {}
    for label in ("phish", "spam", "ham"):
        path = NORM / f"{label}.jsonl"
        if not path.exists():
            continue
        for line in path.open(encoding="utf-8"):
            d = json.loads(line)
            links = [Link(**lk) for lk in d.pop("links", [])]
            attachments = [Attachment(**a) for a in d.pop("attachments", [])]
            rec = EmailRecord(**{k: v for k, v in d.items()
                                 if k in EmailRecord.__dataclass_fields__})
            rec.links, rec.attachments = links, attachments
            by_id[rec.record_id] = rec
    return by_id


def presentable(s: dict) -> bool:
    """Exclude messages whose visible text would mislead a viewer of the demo.

    `phishing@pot` is the recipient address the phishing corpus substitutes into
    every message. It is an artifact of the corpus, not of phishing, and WBS 1.4
    already excludes it from the features - so a demo panel quoting it back
    would be showing the audience something the model never used.

    Non-Latin and non-English subject lines are excluded for the same reason a
    slide is: the room cannot read them, so the explanation cannot be checked
    against the message.
    """
    shown = " ".join([s["subject"], s["body_preview"], s["from_display"]]
                     + [x["text"] for x in s["panel"]["signals"]])
    if "phishing@pot" in shown.lower():
        return False
    subject = s["subject"].strip()
    if not subject:
        return False
    # Readable in the room: the subject line has to be plain English text.
    if sum(ord(c) > 127 for c in subject) > 0:
        return False
    if sum(ord(c) > 127 for c in s["body_preview"]) > len(s["body_preview"]) * 0.01:
        return False
    return is_english(f"{subject} {s['body_preview']}")


ENGLISH_MARKERS = {
    "the", "and", "you", "your", "to", "of", "for", "is", "are", "we", "this",
    "that", "with", "have", "has", "will", "please", "account", "from", "not",
}


def is_english(text: str) -> bool:
    """Cheap language gate - the audience has to be able to read the message.

    The corpora are multilingual. An explanation can only be checked against a
    message the room can read, so a message that does not look like English is
    not a candidate for the demo. This is a presentation constraint, not a
    modelling one: the classifier scores every message either way.
    """
    words = {w.strip(".,!?:;\"'()").lower() for w in text.split()}
    return len(words & ENGLISH_MARKERS) >= 4


def select(scans: list[dict]) -> list[dict]:
    phish = [s for s in scans if s["truth"] == "phish" and presentable(s)]
    ham = [s for s in scans if s["truth"] == "ham" and presentable(s)]

    with_rule = [s for s in phish if any(x["kind"] == "rule" for x in s["panel"]["signals"])]
    picks = []
    if with_rule:
        picks.append(("Caught - phishing, both explanation layers",
                      max(with_rule, key=lambda s: s["panel"]["risk_score"])))
    elif phish:
        picks.append(("Caught - phishing", max(phish, key=lambda s: s["panel"]["risk_score"])))
    if ham:
        picks.append(("Cleared - ordinary mail",
                      min(ham, key=lambda s: s["panel"]["risk_score"])))
    mid = [s for s in phish if s["panel"]["severity"] in ("caution", "suspicious")]
    if mid:
        picks.append(("Near miss - phishing the model was unsure about",
                      min(mid, key=lambda s: s["panel"]["risk_score"])))
    if ham:
        picks.append(("False positive - the worst one in the test set",
                      max(ham, key=lambda s: s["panel"]["risk_score"])))

    out = []
    seen = set()
    for caption, s in picks:
        if s["record_id"] in seen:
            continue
        seen.add(s["record_id"])
        out.append({**s, "caption": caption})
    return out


def scan_all() -> tuple[list[dict], dict]:
    bundle = load_bundle("full")
    records = load_records()
    rows = [json.loads(line) for line in (SPLITS / "test.jsonl").open(encoding="utf-8")]

    scans = []
    for r in rows:
        rec = records.get(r["record_id"])
        if rec is None:
            continue
        panel = explain(rec, r["features"], bundle)
        scans.append({
            "record_id": r["record_id"],
            "truth": r["label_3way"],
            "from_display": rec.from_display,
            "from_address": rec.from_address,
            "subject": rec.subject,
            "body_preview": " ".join((rec.body_text or "").split())[:600],
            "link_count": len(rec.links),
            "panel": panel,
        })
    return scans, bundle


# --------------------------------------------------------------------------- #
# Rendering. Every string from a corpus message is escaped before it reaches
# the page - these are real phishing messages and their markup is not trusted.
# --------------------------------------------------------------------------- #
TIER_COLOR = {
    "dangerous": ("#b3261e", "#fceeed"),
    "suspicious": ("#a15c00", "#fdf3e3"),
    "caution": ("#7a5d00", "#fdf8e3"),
    "clear": ("#136c3a", "#edf7f0"),
}


def e(s: str) -> str:
    return html.escape(s or "", quote=True)


def render_message(i: int, s: dict, active: bool) -> str:
    p = s["panel"]
    fg, bg = TIER_COLOR[p["severity"]]
    signals = "".join(
        f'<li class="sig {x["kind"]}"><span class="tag">{"rule" if x["kind"]=="rule" else "model"}</span>'
        f'<span class="txt">{e(x["text"])}</span>'
        + (f'<span class="share">{round(x["share"]*100)}%</span>' if x.get("share") else "")
        + "</li>"
        for x in p["signals"]) or '<li class="sig none"><span class="txt">No signals above the reporting threshold.</span></li>'
    mitig = "".join(f"<li>{e(m['text'])}</li>" for m in p["mitigating"])
    mitig_block = f'<div class="mitig"><h4>Points the other way</h4><ul>{mitig}</ul></div>' if mitig else ""

    truth = {"phish": "phishing", "ham": "legitimate", "spam": "bulk mail"}[s["truth"]]
    return f'''
<section class="screen{' active' if active else ''}" id="screen-{i}">
  <div class="caption"><strong>{e(s['caption'])}</strong>
    <span class="truth">ground truth: {truth} &middot; held-out test split</span></div>
  <div class="split">
    <div class="mail">
      <div class="subject">{e(s['subject']) or '<em>(no subject)</em>'}</div>
      <div class="from"><span class="avatar">{e((s['from_display'] or s['from_address'] or '?')[:1].upper())}</span>
        <div><div class="name">{e(s['from_display']) or '<em>(no display name)</em>'}</div>
             <div class="addr">&lt;{e(s['from_address'])}&gt;</div></div></div>
      <div class="body">{e(s['body_preview'])}{'&hellip;' if len(s['body_preview']) >= 600 else ''}</div>
      <div class="meta">{s['link_count']} link{'s' if s['link_count'] != 1 else ''} in this message</div>
    </div>
    <aside class="panel">
      <div class="brand">PhishLens</div>
      <div class="verdict" style="background:{bg};color:{fg};border-color:{fg}33">
        <div class="score">{p['risk_score']}<span>/100</span></div>
        <div class="tier">{p['severity'].upper()}</div>
        <div class="headline">{e(p['headline'])}</div>
      </div>
      <p class="advice">{e(p['advice'])}</p>
      <h4>Why</h4>
      <ul class="signals">{signals}</ul>
      {mitig_block}
      <div class="foot">{p['signals_considered']} features considered &middot;
        percentages are each signal's share of the model's evidence toward phishing</div>
    </aside>
  </div>
</section>'''


def render(selected: list[dict], bundle: dict, metrics: dict) -> str:
    tabs = "".join(
        f'<button class="tab{" active" if i == 0 else ""}" data-i="{i}">{e(s["caption"].split(" - ")[0])}</button>'
        for i, s in enumerate(selected))
    screens = "".join(render_message(i, s, i == 0) for i, s in enumerate(selected))
    m = metrics["at_tier_thresholds"]["dangerous"]
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>PhishLens - IM1 demo</title>
<style>
  :root {{ --line:#dadce0; --ink:#202124; --muted:#5f6368; --bg:#f6f8fc; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--bg); color:var(--ink);
         font:15px/1.55 -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif; }}
  header {{ padding:22px 28px 14px; }}
  h1 {{ margin:0; font-size:21px; font-weight:600; }}
  header p {{ margin:4px 0 0; color:var(--muted); font-size:13px; }}
  .tabs {{ display:flex; gap:8px; padding:12px 28px 0; flex-wrap:wrap; }}
  .tab {{ border:1px solid var(--line); background:#fff; border-radius:999px;
          padding:7px 15px; font-size:13px; cursor:pointer; color:var(--muted); }}
  .tab.active {{ background:var(--ink); border-color:var(--ink); color:#fff; }}
  .screen {{ display:none; padding:14px 28px 32px; }}
  .screen.active {{ display:block; }}
  .caption {{ font-size:13px; color:var(--muted); margin:10px 0 12px; }}
  .caption strong {{ color:var(--ink); }}
  .truth {{ margin-left:10px; }}
  .split {{ display:grid; grid-template-columns:1fr 340px; gap:18px; align-items:stretch; }}
  .mail, .panel {{ background:#fff; border:1px solid var(--line); border-radius:12px; padding:20px; }}
  .panel {{ align-self:start; }}
  .mail {{ display:flex; flex-direction:column; }}
  .body {{ flex:1; }}
  .subject {{ font-size:20px; margin-bottom:14px; word-break:break-word; }}
  .from {{ display:flex; gap:11px; align-items:center; padding-bottom:14px;
           border-bottom:1px solid var(--line); margin-bottom:14px; }}
  .avatar {{ width:36px; height:36px; border-radius:50%; background:#5f6368; color:#fff;
             display:grid; place-items:center; font-weight:600; flex:none; }}
  .name {{ font-weight:600; font-size:14px; }}
  .addr {{ color:var(--muted); font-size:12px; word-break:break-all; }}
  .body {{ white-space:pre-wrap; word-break:break-word; font-size:14px; color:#3c4043; }}
  .meta {{ margin-top:14px; font-size:12px; color:var(--muted); }}
  .brand {{ font-weight:600; letter-spacing:.3px; font-size:13px;
            text-transform:uppercase; color:var(--muted); margin-bottom:12px; }}
  .verdict {{ border:1px solid; border-radius:10px; padding:14px; text-align:center; }}
  .score {{ font-size:34px; font-weight:700; line-height:1; }}
  .score span {{ font-size:14px; font-weight:500; opacity:.65; }}
  .tier {{ font-size:11px; letter-spacing:1.4px; margin-top:6px; font-weight:700; }}
  .headline {{ font-size:13px; margin-top:6px; }}
  .advice {{ font-size:13px; color:var(--muted); margin:12px 0 4px; }}
  .panel h4 {{ font-size:12px; text-transform:uppercase; letter-spacing:.6px;
               color:var(--muted); margin:16px 0 8px; }}
  ul {{ list-style:none; margin:0; padding:0; }}
  .sig {{ display:flex; gap:8px; align-items:baseline; padding:8px 0;
          border-top:1px solid #eceff1; font-size:13px; }}
  .tag {{ font-size:9px; letter-spacing:.7px; text-transform:uppercase; padding:2px 5px;
          border-radius:4px; background:#eceff1; color:var(--muted); flex:none; }}
  .sig.rule .tag {{ background:#e8eaf6; color:#3949ab; }}
  .txt {{ flex:1; }}
  .share {{ color:var(--muted); font-size:11px; flex:none; }}
  .mitig ul li {{ font-size:13px; color:#3c4043; padding:6px 0; border-top:1px solid #eceff1; }}
  .foot {{ margin-top:16px; font-size:11px; color:var(--muted); line-height:1.5; }}
  footer {{ padding:0 28px 40px; color:var(--muted); font-size:12px; max-width:900px; }}
  code {{ background:#fff; border:1px solid var(--line); border-radius:4px; padding:1px 5px; }}
  @media (max-width:860px) {{ .split {{ grid-template-columns:1fr; }} }}
</style></head><body>
<header>
  <h1>PhishLens &mdash; explanation panel, driven by the real model</h1>
  <p>Generated {generated} by <code>06_Deliverables/IM1_demo/scan_demo.py</code>.
     Messages are from the held-out test split; the model never saw them in training.
     Scores, tiers and sentences are produced by WBS 2.1&ndash;2.3 at render time &mdash; none are written by hand.</p>
</header>
<div class="tabs">{tabs}</div>
{screens}
<footer>
  Model: logistic regression on {bundle['n_features']} named features, trained on {bundle['n_train']}
  campaign-split messages. At the <strong>dangerous</strong> threshold the model reaches
  precision {m['precision']}, recall {m['recall']}, and a false-positive rate of
  {m['fpr_ham']:.1%} on ordinary correspondence. The panel layout previews WBS 4.3;
  the extension itself is week 6&ndash;7 work.
</footer>
<script>
  document.querySelectorAll('.tab').forEach(function (t) {{
    t.addEventListener('click', function () {{
      document.querySelectorAll('.tab').forEach(function (x) {{ x.classList.remove('active'); }});
      document.querySelectorAll('.screen').forEach(function (x) {{ x.classList.remove('active'); }});
      t.classList.add('active');
      document.getElementById('screen-' + t.dataset.i).classList.add('active');
    }});
  }});
</script>
</body></html>'''


def main() -> None:
    scans, bundle = scan_all()
    selected = select(scans)
    metrics = json.loads((ROOT / "02_Model" / "results" / "metrics_full.json").read_text(encoding="utf-8"))

    (OUT / "scan_results.json").write_text(
        json.dumps({"generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "model_variant": bundle["variant"],
                    "n_scanned": len(scans),
                    "selected": selected}, indent=2), encoding="utf-8")
    (OUT / "PhishLens_IM1_demo.html").write_text(render(selected, bundle, metrics), encoding="utf-8")

    print(f"scanned {len(scans)} held-out messages")
    for s in selected:
        p = s["panel"]
        print(f"  {s['caption'][:46]:<48} {p['risk_score']:>3}/100  {p['severity']:<10} "
              f"{len(p['signals'])} signals  (truth: {s['truth']})")
    print(f"\nwrote {OUT / 'PhishLens_IM1_demo.html'}")


if __name__ == "__main__":
    main()
