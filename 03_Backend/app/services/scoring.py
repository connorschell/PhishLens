"""WBS 3.3 - the scoring service.

This is the seam where the work of weeks two to four becomes an API. It runs
exactly the chain the demo runs, in the same order, through the same modules:

    payload -> parse_email.parse_gmail_payload   (WBS 1.3)
            -> features.extract_features         (WBS 1.4)
            -> contributions.score_features      (WBS 2.2)
            -> explain.explain                   (WBS 2.3)

There is deliberately no second implementation of any step. The parser the
extension's payload goes through is the parser the training corpus went
through, which is the whole reason WBS 1.3 was factored out as a module with
two entry points.
"""

from __future__ import annotations

import hashlib
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
for p in (ROOT / "01_Data" / "src", ROOT / "02_Model"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from features import extract_features                      # noqa: E402
from parse_email import parse_gmail_payload                # noqa: E402

import contributions as contrib                            # noqa: E402
import explain as explain_mod                              # noqa: E402

from ..config import get_settings                          # noqa: E402


class ModelUnavailable(RuntimeError):
    """No trained bundle on disk. The API refuses to guess."""


@lru_cache
def get_bundle() -> dict[str, Any]:
    settings = get_settings()
    try:
        return contrib.load_bundle(settings.model_variant)
    except FileNotFoundError as exc:                       # pragma: no cover
        raise ModelUnavailable(
            f"no model bundle for variant {settings.model_variant!r}; "
            "run 02_Model/train_baseline.py") from exc


def fingerprint(subject: str, body_text: str) -> bytes:
    """Salted digest of the message, so a re-scan is recognisable and the
    message is not recoverable. See 00_Admin/data-handling.md."""
    salt = get_settings().fingerprint_salt.encode("utf-8")
    norm = " ".join((subject or "").split()).lower() + "\n" + \
           " ".join((body_text or "").split()).lower()
    return hashlib.sha256(salt + norm.encode("utf-8", errors="replace")).digest()


def score(payload: dict[str, Any]) -> dict[str, Any]:
    """Score one message. Returns the panel plus what the database needs."""
    bundle = get_bundle()
    record = parse_gmail_payload(payload)
    feats = extract_features(record)
    panel = explain_mod.explain(record, feats, bundle)
    return {
        "panel": panel,
        "features": feats,
        "fingerprint": fingerprint(payload.get("subject", ""),
                                   payload.get("body_text", "")),
        "bundle": bundle,
    }
