"""WBS 2.1 - evaluation harness.

Reports precision, recall, and false-positive rate. Never accuracy: the test
split is 53.7% phishing and an inbox is not, so an accuracy figure here would
describe the corpus rather than the tool.

Three false-positive rates are reported, not one:

    fpr_overall  legitimate mail of any kind scored as phishing
    fpr_ham      ordinary correspondence scored as phishing  <- the number that
                 decides whether the extension is tolerable in daily use
    fpr_spam     unsolicited bulk mail scored as phishing    <- a much cheaper
                 mistake, reported separately so it cannot flatter fpr_ham

Run after train_baseline.py:
    python 02_Model/evaluate.py
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from sklearn.metrics import average_precision_score, roc_auc_score

ROOT = Path(__file__).resolve().parents[1]
SPLITS = ROOT / "01_Data" / "processed" / "splits"
RESULTS = Path(__file__).resolve().parent / "results"


def load_bundle(variant: str) -> dict:
    return json.loads((RESULTS / f"model_{variant}.json").read_text(encoding="utf-8"))


def load_test(bundle: dict):
    rows = [json.loads(line) for line in (SPLITS / "test.jsonl").open(encoding="utf-8")]
    names = bundle["feature_names"]
    X = np.array([[r["features"][n] for n in names] for r in rows], dtype=float)
    y = np.array([r["label"] for r in rows], dtype=int)
    label3 = [r["label_3way"] for r in rows]
    return rows, X, y, label3


def predict_proba(bundle: dict, X: np.ndarray) -> np.ndarray:
    z = (X - np.array(bundle["mean"])) / np.array(bundle["std"])
    logit = z @ np.array(bundle["coef"]) + bundle["intercept"]
    return 1.0 / (1.0 + np.exp(-logit))


def metrics_at(p: np.ndarray, y: np.ndarray, label3: list[str], t: float) -> dict:
    pred = (p >= t).astype(int)
    tp = int(((pred == 1) & (y == 1)).sum())
    fp = int(((pred == 1) & (y == 0)).sum())
    fn = int(((pred == 0) & (y == 1)).sum())
    tn = int(((pred == 0) & (y == 0)).sum())

    def fpr_for(group: str) -> float:
        idx = [i for i, l in enumerate(label3) if l == group]
        if not idx:
            return 0.0
        return round(float(np.mean(pred[idx] == 1)), 4)

    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "threshold": round(float(t), 4),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "fpr_overall": round(fp / (fp + tn), 4) if fp + tn else 0.0,
        "fpr_ham": fpr_for("ham"),
        "fpr_spam": fpr_for("spam"),
        "confusion": {"tp": tp, "fp": fp, "fn": fn, "tn": tn},
    }


def evaluate(variant: str) -> dict:
    bundle = load_bundle(variant)
    rows, X, y, label3 = load_test(bundle)
    p = predict_proba(bundle, X)

    tiers = bundle["severity_tiers"]
    tier_counts = {k: 0 for k in ["clear", "caution", "suspicious", "dangerous"]}
    tier_of = []
    for prob in p:
        if prob >= tiers["dangerous"]:
            t = "dangerous"
        elif prob >= tiers["suspicious"]:
            t = "suspicious"
        elif prob >= tiers["caution"]:
            t = "caution"
        else:
            t = "clear"
        tier_of.append(t)
        tier_counts[t] += 1

    tier_purity = {}
    for name in tier_counts:
        idx = [i for i, t in enumerate(tier_of) if t == name]
        tier_purity[name] = {
            "n": len(idx),
            "pct_phishing": round(float(np.mean(y[idx] == 1)) * 100, 1) if idx else None,
        }

    gbm_path = RESULTS / f"gbm_test_proba_{variant}.npy"
    gbm_ref = None
    if gbm_path.exists():
        gp = np.load(gbm_path)
        gbm_ref = {
            "roc_auc": round(float(roc_auc_score(y, gp)), 4),
            "pr_auc": round(float(average_precision_score(y, gp)), 4),
        }

    coef = np.array(bundle["coef"])
    order = np.argsort(-np.abs(coef))[:12]
    top_weights = [{"feature": bundle["feature_names"][i], "weight": round(float(coef[i]), 3)}
                   for i in order]

    out = {
        "variant": variant,
        "evaluated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "n_test": int(len(y)),
        "n_features": bundle["n_features"],
        "ablated_features": bundle["ablated_features"],
        "ranking": {
            "roc_auc": round(float(roc_auc_score(y, p)), 4),
            "pr_auc": round(float(average_precision_score(y, p)), 4),
        },
        "gbm_reference": gbm_ref,
        "at_decision_threshold": metrics_at(p, y, label3, bundle["decision_threshold"]),
        "at_tier_thresholds": {k: metrics_at(p, y, label3, v) for k, v in tiers.items()},
        "threshold_sweep": [metrics_at(p, y, label3, t) for t in np.arange(0.1, 0.96, 0.05)],
        "severity_tier_distribution": tier_purity,
        "top_weights_by_magnitude": top_weights,
    }
    (RESULTS / f"metrics_{variant}.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    return out


def matched(result: dict, ham_fpr_budget: float) -> dict:
    """The sweep row with the highest recall whose ham FPR stays within budget."""
    ok = [r for r in result["threshold_sweep"] if r["fpr_ham"] <= ham_fpr_budget]
    if not ok:
        return min(result["threshold_sweep"], key=lambda r: r["fpr_ham"])
    return max(ok, key=lambda r: r["recall"])


def write_comparison(full: dict, ablated: dict) -> None:
    def row(label, a, b):
        return f"| {label} | {a} | {b} |"

    f, a = full["at_decision_threshold"], ablated["at_decision_threshold"]
    lines = [
        "# WBS 2.1 - baseline results",
        "",
        f"Generated {full['evaluated_utc']}. Test split: {full['n_test']} held-out messages, "
        "campaign-aware, measured leakage 0%.",
        "",
        "Accuracy is not reported. The test split is 53.7% phishing and an inbox is not.",
        "",
        "## Full feature set vs ablated",
        "",
        "The ablated run removes the six features whose single-feature AUC in WBS 1.5 "
        "suggested they were separating the 2002 ham corpus from the 2022+ phishing corpus "
        "rather than separating phishing from legitimate mail: "
        + ", ".join(f"`{n}`" for n in ablated["ablated_features"]) + ".",
        "",
        f"| Metric | Full ({full['n_features']} features) | Ablated ({ablated['n_features']} features) |",
        "|---|---|---|",
        row("Precision", f["precision"], a["precision"]),
        row("Recall", f["recall"], a["recall"]),
        row("False-positive rate, ham", f["fpr_ham"], a["fpr_ham"]),
        row("False-positive rate, spam", f["fpr_spam"], a["fpr_spam"]),
        row("False-positive rate, overall", f["fpr_overall"], a["fpr_overall"]),
        row("ROC AUC", full["ranking"]["roc_auc"], ablated["ranking"]["roc_auc"]),
        row("PR AUC", full["ranking"]["pr_auc"], ablated["ranking"]["pr_auc"]),
        "",
        "The two runs above sit at each variant's own tier thresholds, which differ. "
        "The table below removes that difference by holding the false-positive rate on "
        "ordinary correspondence equal and comparing what each model catches at that cost - "
        "the comparison that actually matters, since a user picks a tolerance, not a threshold.",
        "",
        "| Matched operating point | Full | Ablated |",
        "|---|---|---|",
    ]
    for budget in (0.01, 0.05, 0.10):
        mf = matched(full, budget)
        ma = matched(ablated, budget)
        lines.append(
            f"| Recall at {budget:.0%} ham FPR | {mf['recall']} (P {mf['precision']}) "
            f"| {ma['recall']} (P {ma['precision']}) |")
    lines += [
        "",
        "## Reference ceiling",
        "",
        "A gradient-boosted tree ensemble trained on the same features, evaluated only to "
        "measure what explainability costs. It is not shipped: it offers no exact per-feature "
        "contribution, which WBS 2.2 and 2.3 require.",
        "",
        "| Variant | Logistic PR AUC | GBM PR AUC |",
        "|---|---|---|",
        row("Full", full["ranking"]["pr_auc"], (full["gbm_reference"] or {}).get("pr_auc")),
        row("Ablated", ablated["ranking"]["pr_auc"], (ablated["gbm_reference"] or {}).get("pr_auc")),
        "",
        "## Severity tiers",
        "",
        "Thresholds are set on out-of-fold training predictions against a false-positive "
        "budget on ordinary correspondence, not on round numbers: "
        + ", ".join(f"{k} <= {v:.1%} ham FPR" for k, v in
                    json.loads((RESULTS / 'model_full.json').read_text())['tier_ham_fpr_budget'].items())
        + ".",
        "",
        "| Tier | Threshold | Test messages | % actually phishing |",
        "|---|---|---|---|",
    ]
    tiers = json.loads((RESULTS / "model_full.json").read_text())["severity_tiers"]
    for name in ["clear", "caution", "suspicious", "dangerous"]:
        d = full["severity_tier_distribution"][name]
        thr = "-" if name == "clear" else f"{tiers[name]:.3f}"
        lines.append(f"| {name} | {thr} | {d['n']} | {d['pct_phishing']} |")
    lines += ["", "## Strongest learned weights (full model)", "",
              "| Feature | Standardised weight |", "|---|---|"]
    for w in full["top_weights_by_magnitude"]:
        lines.append(f"| `{w['feature']}` | {w['weight']} |")
    lines.append("")
    (RESULTS / "baseline_results.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", choices=["full", "ablated", "both"], default="both")
    args = ap.parse_args()
    if args.variant == "both":
        full, ablated = evaluate("full"), evaluate("ablated")
        write_comparison(full, ablated)
        for d in (full, ablated):
            m = d["at_decision_threshold"]
            print(f"[{d['variant']:>7}] precision {m['precision']:.3f}  recall {m['recall']:.3f}  "
                  f"ham FPR {m['fpr_ham']:.3f}  spam FPR {m['fpr_spam']:.3f}  "
                  f"PR AUC {d['ranking']['pr_auc']:.3f}")
    else:
        print(json.dumps(evaluate(args.variant)["at_decision_threshold"], indent=2))


if __name__ == "__main__":
    main()
