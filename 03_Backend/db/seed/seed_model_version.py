"""WBS 3.2 - register a trained model bundle in the database.

The API refuses to score if no model version is active, by design: a scan whose
model cannot be named later is a scan that cannot be explained later. This
script reads a bundle produced by WBS 2.1 and records it.

    python 03_Backend/db/seed/seed_model_version.py --variant full --activate
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[3]
RESULTS = ROOT / "02_Model" / "results"


def load(variant: str) -> tuple[dict, bytes]:
    raw = (RESULTS / f"model_{variant}.json").read_bytes()
    return json.loads(raw), hashlib.sha256(raw).digest()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", choices=["full", "ablated"], default="full")
    ap.add_argument("--activate", action="store_true",
                    help="make this the model the API scores with")
    ap.add_argument("--database-url", default=os.environ.get("DATABASE_URL"))
    args = ap.parse_args()
    if not args.database_url:
        sys.exit("DATABASE_URL is not set and --database-url was not given")

    bundle, digest = load(args.variant)
    engine = create_engine(args.database_url, future=True)

    with engine.begin() as cx:
        row = cx.execute(text("SELECT model_version_id FROM model_versions "
                              "WHERE bundle_sha256 = :d"), {"d": digest}).first()
        if row:
            mvid = row[0]
            print(f"bundle already registered as model_version_id {mvid}")
        else:
            mvid = cx.execute(text("""
                INSERT INTO model_versions
                    (variant, trained_utc, n_features, n_train, bundle_sha256, severity_tiers)
                VALUES (:v, :t, :nf, :nt, :d, CAST(:tiers AS jsonb))
                RETURNING model_version_id
            """), {
                "v": bundle["variant"],
                "t": datetime.fromisoformat(bundle["trained_utc"]),
                "nf": bundle["n_features"],
                "nt": bundle["n_train"],
                "d": digest,
                "tiers": json.dumps(bundle["severity_tiers"]),
            }).scalar_one()
            print(f"registered {args.variant} bundle as model_version_id {mvid}")

        if args.activate:
            cx.execute(text("UPDATE model_versions SET is_active = false WHERE is_active"))
            cx.execute(text("UPDATE model_versions SET is_active = true, loaded_at = now() "
                            "WHERE model_version_id = :i"), {"i": mvid})
            print(f"model_version_id {mvid} is now active")


if __name__ == "__main__":
    main()
