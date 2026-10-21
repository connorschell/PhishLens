"""WBS 3.3 - POST /scan.

Scores one message and records the result. Authentication is accepted here but
not enforced: /register and per-install tokens land in WBS 3.4, and until they
exist an unauthenticated scan is still scored so the extension work in week six
is not blocked on it. The hook is in place so turning enforcement on is a
one-line change rather than a refactor.
"""

from __future__ import annotations

import hashlib
import logging
import time

from fastapi import APIRouter, Header, HTTPException, status
from sqlalchemy import text

from ..db import session_scope
from ..schemas import ScanRequest, ScanResponse
from ..services.scoring import ModelUnavailable, score

log = logging.getLogger(__name__)
router = APIRouter(tags=["scan"])


def _install_id(session, authorization: str | None):
    """Resolve a bearer token to an install, if one was sent and matches."""
    if not session or not authorization or not authorization.lower().startswith("bearer "):
        return None
    token = authorization.split(" ", 1)[1].strip()
    digest = hashlib.sha256(token.encode("utf-8")).digest()
    row = session.execute(
        text("SELECT install_id FROM installs "
             "WHERE token_hash = :d AND revoked_at IS NULL"),
        {"d": digest}).first()
    if row:
        session.execute(
            text("UPDATE installs SET last_seen_at = now() WHERE install_id = :i"),
            {"i": row[0]})
        return row[0]
    return None


def _persist(result, duration_ms, authorization):
    """Record the scan. Returns a scan id, or None if nothing was recorded.

    A failure here is logged and swallowed: the verdict has already been
    computed and withholding it because history could not be written would be
    the wrong trade.
    """
    panel = result["panel"]
    try:
        with session_scope() as session:
            if session is None:
                return None
            mv = session.execute(
                text("SELECT model_version_id FROM model_versions WHERE is_active")).first()
            if mv is None:
                log.warning("no active model_version row; scan not recorded")
                return None

            install_id = _install_id(session, authorization)
            scan_id = session.execute(text("""
                INSERT INTO scans (install_id, model_version_id, message_fingerprint,
                                   risk_score, probability, severity, features, duration_ms)
                VALUES (:install, :mv, :fp, :score, :prob, :sev, CAST(:feats AS jsonb), :ms)
                RETURNING scan_id
            """), {
                "install": install_id,
                "mv": mv[0],
                "fp": result["fingerprint"],
                "score": panel["risk_score"],
                "prob": panel["probability"],
                "sev": panel["severity"],
                "feats": __import__("json").dumps(result["features"]),
                "ms": duration_ms,
            }).scalar_one()

            for rank, sig in enumerate(panel["signals"]):
                session.execute(text("""
                    INSERT INTO indicators (scan_id, rank, kind, feature, rule,
                                            display_text, share, contribution)
                    VALUES (:s, :r, :k, :f, :rule, :t, :share, :c)
                """), {
                    "s": scan_id, "r": rank, "k": sig["kind"],
                    "f": sig.get("feature"), "rule": sig.get("rule"),
                    "t": sig["text"], "share": sig.get("share"),
                    "c": sig.get("contribution"),
                })
            return scan_id
    except Exception:
        log.exception("scan not recorded")
        return None


@router.post("/scan", response_model=ScanResponse)
def scan(req: ScanRequest, authorization: str | None = Header(default=None)) -> ScanResponse:
    started = time.perf_counter()
    try:
        result = score(req.model_dump())
    except ModelUnavailable as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc

    duration_ms = int((time.perf_counter() - started) * 1000)
    panel = result["panel"]
    scan_id = _persist(result, duration_ms, authorization)

    return ScanResponse(
        scan_id=scan_id,
        risk_score=panel["risk_score"],
        severity=panel["severity"],
        headline=panel["headline"],
        advice=panel["advice"],
        signals=panel["signals"],
        mitigating=panel["mitigating"],
        model_variant=panel["model_variant"],
        signals_considered=panel["signals_considered"],
        persisted=scan_id is not None,
        duration_ms=duration_ms,
    )
