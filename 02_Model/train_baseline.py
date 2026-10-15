"""WBS 2.1 - baseline classifier and model bundle.

Trains the model the rest of the system is built on and writes a self-contained
bundle that WBS 2.2, 2.3, and the WBS 3.3 /scan endpoint all load.

Why logistic regression is the primary model
--------------------------------------------
The project's defining requirement is that every verdict comes with
explanations derived from *real* model contributions (WBS 2.2/2.3), not from a
post-hoc approximation bolted onto an opaque model. A linear model on
standardised features gives an exact additive decomposition:

    logit(p) = b0 + SUM_i ( w_i * z_i )      z_i = (x_i - mean_i) / std_i

Each term is that feature's contribution, it is exact rather than estimated,
and it costs nothing at inference time - which matters for a browser extension
waiting on a scan. A gradient-boosted model is trained alongside purely as a
reference ceiling: if the tree ensemble is far ahead, that gap is reported in
the final report as the price paid for explainability. It is not shipped.

Two variants, always
--------------------
Six features showed high single-feature AUC in WBS 1.5 and are suspected of
measuring the 20-year gap between the ham corpus (2002) and the phishing corpus
(2022+) rather than phishing itself. Every run trains and evaluates both:

    full     all 43 features
    ablated  those six removed

If the ablated numbers collapse, the model was reading the corpus gap. The
comparison goes in the final report either way.

Usage:
    python 02_Model/train_baseline.py              # both variants
    python 02_Model/train_baseline.py --variant full
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold, cross_val_predict

ROOT = Path(__file__).resolve().parents[1]
SPLITS = ROOT / "01_Data" / "processed" / "splits"
RESULTS = Path(__file__).resolve().parent / "results"

# The six features under suspicion from the WBS 1.5 single-feature AUC report.
ABLATION_FEATURES = [
    "has_http_only_link",
    "link_density_per_100_words",
    "max_url_length",
    "subject_has_reply_prefix",
    "subject_length",
    "subject_nonascii",
]

# Severity tiers are set from the false-positive rate on legitimate mail, not
# from round numbers. A user tolerates a wrong "dangerous" banner far less than
# a wrong "caution" one, so each tier gets a ham false-positive budget and the
# threshold is whatever probability meets it on held-out-by-fold predictions.
TIER_HAM_FPR_BUDGET = {
    "dangerous": 0.005,
    "suspicious": 0.02,
    "caution": 0.10,
}

SEED = 20260930


def load_split(name: str) -> tuple[list[dict], np.ndarray, np.ndarray, list[str]]:
    rows = [json.loads(line) for line in (SPLITS / f"{name}.jsonl").open(encoding="utf-8")]
    names = list(rows[0]["features"].keys())
    X = np.array([[r["features"][n] for n in names] for r in rows], dtype=float)
    y = np.array([r["label"] for r in rows], dtype=int)
    return rows, X, y, names


def select(X: np.ndarray, names: list[str], keep: list[str]) -> np.ndarray:
    idx = [names.index(n) for n in keep]
    return X[:, idx]


def threshold_for_ham_fpr(p: np.ndarray, label3: list[str], budget: float) -> float:
    """Lowest probability whose ham false-positive rate stays within budget.

    Measured on ham only. Spam false positives are reported separately and
    deliberately not budgeted here: calling unsolicited bulk mail suspicious is
    a far smaller wrong than calling a colleague's mail suspicious.
    """
    ham = np.array([p[i] for i, l in enumerate(label3) if l == "ham"])
    if ham.size == 0:
        return 0.5
    # quantile of the ham score distribution that leaves `budget` above it
    return float(np.quantile(ham, 1.0 - budget))


def train_variant(variant: str, verbose: bool = True) -> dict:
    train_rows, Xtr_all, ytr, names = load_split("train")
    keep = [n for n in names if not (variant == "ablated" and n in ABLATION_FEATURES)]
    Xtr = select(Xtr_all, names, keep)

    mean = Xtr.mean(axis=0)
    std = Xtr.std(axis=0)
    std[std == 0] = 1.0           # constant column contributes nothing, never NaN
    Ztr = (Xtr - mean) / std

    model = LogisticRegression(
        penalty="l2",
        C=1.0,
        solver="lbfgs",
        max_iter=2000,
        class_weight="balanced",   # phishing is 53.7% here but will not be in an inbox
        random_state=SEED,
    )
    model.fit(Ztr, ytr)

    # Out-of-fold probabilities on the training set: thresholds and tiers are
    # chosen here so the test set stays genuinely held out.
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=SEED)
    oof = cross_val_predict(model, Ztr, ytr, cv=cv, method="predict_proba")[:, 1]
    label3 = [r["label_3way"] for r in train_rows]

    tiers = {k: threshold_for_ham_fpr(oof, label3, b)
             for k, b in TIER_HAM_FPR_BUDGET.items()}
    # Tiers must be monotone even if the ham distribution is flat in places.
    tiers["suspicious"] = min(tiers["suspicious"], tiers["dangerous"])
    tiers["caution"] = min(tiers["caution"], tiers["suspicious"])

    # Reference ceiling only. Never shipped - no exact contributions available.
    gbm = HistGradientBoostingClassifier(random_state=SEED, max_iter=300)
    gbm.fit(Xtr, ytr)

    bundle = {
        "variant": variant,
        "trained_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "seed": SEED,
        "model": "logistic_regression_l2_balanced",
        "feature_names": keep,
        "mean": mean.tolist(),
        "std": std.tolist(),
        "coef": model.coef_[0].tolist(),
        "intercept": float(model.intercept_[0]),
        "decision_threshold": float(tiers["caution"]),
        "severity_tiers": tiers,
        "tier_ham_fpr_budget": TIER_HAM_FPR_BUDGET,
        "n_train": int(Xtr.shape[0]),
        "n_features": len(keep),
        "ablated_features": ABLATION_FEATURES if variant == "ablated" else [],
    }

    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / f"model_{variant}.json").write_text(json.dumps(bundle, indent=2), encoding="utf-8")

    # The GBM reference numbers travel with the evaluation, not the bundle.
    _, Xte_all, yte, te_names = load_split("test")
    Xte = select(Xte_all, te_names, keep)
    np.save(RESULTS / f"gbm_test_proba_{variant}.npy", gbm.predict_proba(Xte)[:, 1])

    if verbose:
        print(f"[{variant}] {len(keep)} features, {Xtr.shape[0]} training records")
        print(f"[{variant}] tiers: " + ", ".join(f"{k}>={v:.3f}" for k, v in
                                                 sorted(tiers.items(), key=lambda kv: kv[1])))
    return bundle


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", choices=["full", "ablated", "both"], default="both")
    args = ap.parse_args()
    variants = ["full", "ablated"] if args.variant == "both" else [args.variant]
    for v in variants:
        train_variant(v)
    print(f"\nBundles written to {RESULTS}")


if __name__ == "__main__":
    main()
