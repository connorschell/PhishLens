"""WBS 3.3 - POST /scan, with WBS 3.4 authentication and rate limiting.

Scores one message and records the result.

Authentication is enforced when settings.require_auth is on (the default). The
install is resolved before scoring so a revoked or unrecognised token is
rejected without spending model time on it. The exception is the degraded path:
the installs table is the token store, so when the database is unreachable the
server cannot verify a token at all. It scores the message anyway and records
nothing, because withholding a phishing warning over a database outage is the
wrong trade, and the per-IP rate limit is what remains in force. app/auth.py
carries the full note on that choice.
"""

from __future__ import annotations

import json
import logging
import time

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text

from ..auth import Revoked, authorization_header, bearer_token, resolve_install, unauthorized
from ..config import get_settings
from ..db import session_scope
from ..ratelimit import scan_limit
from ..schemas import ScanRequest, ScanResponse
from ..services.scoring import ModelUnavailable, score

log = logging.getLogger(__name__)
router = APIRouter(tags=["scan"])


def _authenticate(token: str | None) -> tuple[str | None, bool]:
    """Resolve the caller to an install id.

    Returns (install_id, store_reachable). A false second element means the
    token store could not be consulted, which is what puts the request on the
    degraded path rather than producing a 401.
    """
    settings = get_settings()
    if settings.require_auth and not token:
        raise unauthorized("a per-install token is required; call /register first")

    try:
        with session_scope() as session:
            if session is None:
                return None, False
            try:
                install = resolve_install(session, token)
            except Revoked as exc:
                raise unauthorized("this install has been revoked") from exc
            if install is None:
                if settings.require_auth:
                    raise unauthorized("unrecognised install token")
                return None, True
            return install.install_id, True
    except HTTPException:
        raise
    except Exception:
        log.warning("token store unreachable; scoring unauthenticated and not recording")
        return None, False


def _persist(result, duration_ms, install_id):
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
                "feats": json.dumps(result["features"]),
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


@router.post("/scan", response_model=ScanResponse,
             dependencies=[Depends(scan_limit)])
def scan(
    req: ScanRequest,
    authorization: str | None = Depends(authorization_header),
) -> ScanResponse:
    install_id, _store_ok = _authenticate(bearer_token(authorization))

    started = time.perf_counter()
    try:
        result = score(req.model_dump())
    except ModelUnavailable as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc

    duration_ms = int((time.perf_counter() - started) * 1000)
    panel = result["panel"]
    scan_id = _persist(result, duration_ms, install_id)

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
        model_severity=panel["model_severity"],
        severity_floored_by=panel["severity_floored_by"],
    )
