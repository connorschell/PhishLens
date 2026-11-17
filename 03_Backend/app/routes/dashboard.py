"""WBS 4.5 - operator dashboard API.

Read endpoints over what the service has already recorded, plus the one write
the review workflow needs (marking a piece of feedback as seen). The page that
consumes these lives at app/static/dashboard/.

Three things shape this module:

1. Everything here is behind the password gate in app/admin_auth.py. These
   routes aggregate across installs, which no per-install token may do.
2. There is no degraded path. /scan refuses to withhold a verdict when the
   database is down, because a user is waiting on a security decision; a
   dashboard is a convenience and an honest 503 is the correct answer.
3. The queries can only return what the schema stores. No join reaches a
   subject, a body or a sender, because no column holds one. The
   `install_id_short` field is truncated to 8 characters: enough to see that
   three scans came from the same install, not enough to use as an identifier.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import text

from ..admin_auth import (
    DashboardDisabled,
    check_password,
    dashboard_available,
    issue_session,
    require_dashboard_session,
    unavailable,
)
from ..config import get_settings
from ..db import session_scope
from ..ratelimit import dashboard_login_limit
from ..schemas import (
    DashboardLoginRequest,
    DashboardLoginResponse,
    FeedbackItem,
    FeedbackListResponse,
    MetricsResponse,
    ScanListResponse,
    ScanSummary,
    SeverityCount,
)

log = logging.getLogger(__name__)
router = APIRouter(prefix="/dashboard/api", tags=["dashboard"])

_GUARD = [Depends(require_dashboard_session)]


def _iso(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _require_db(session):
    if session is None:
        raise unavailable("dashboard unavailable: no database configured")
    return session


# ------------------------------------------------------------------ login --

@router.post("/login", response_model=DashboardLoginResponse,
             dependencies=[Depends(dashboard_login_limit)])
def login(req: DashboardLoginRequest) -> DashboardLoginResponse:
    """Exchange the operator password for a short-lived session token.

    A wrong password and an unconfigured dashboard are different failures and
    are reported differently (401 vs 503): telling an operator "wrong password"
    when the real problem is an unset environment variable sends them hunting
    for the wrong thing.
    """
    if not dashboard_available():
        raise unavailable(
            "dashboard is not configured on this deployment "
            "(DASHBOARD_PASSWORD / TOKEN_SIGNING_SECRET unset)")
    try:
        if not check_password(req.password):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "incorrect password")
        token, expires_at = issue_session()
    except DashboardDisabled as exc:               # pragma: no cover - guarded above
        raise unavailable(str(exc)) from exc

    return DashboardLoginResponse(
        token=token,
        expires_at=datetime.fromtimestamp(expires_at, tz=UTC).isoformat(),
    )


# ---------------------------------------------------------- scan history --

_SCAN_ROWS = """
    SELECT s.scan_id,
           s.scored_at,
           s.risk_score,
           s.severity,
           s.duration_ms,
           s.install_id,
           mv.variant,
           (SELECT i.display_text
              FROM indicators i
             WHERE i.scan_id = s.scan_id
             ORDER BY i.rank
             LIMIT 1)                             AS top_signal,
           EXISTS (SELECT 1 FROM feedback f
                    WHERE f.scan_id = s.scan_id)  AS has_feedback
      FROM scans s
      JOIN model_versions mv ON mv.model_version_id = s.model_version_id
     WHERE (:severity = '' OR s.severity = :severity)
     ORDER BY s.scored_at DESC
     LIMIT :limit OFFSET :offset
"""


@router.get("/scans", response_model=ScanListResponse, dependencies=_GUARD)
def list_scans(
    page: int = Query(default=1, ge=1, le=10_000),
    severity: str = Query(default="", pattern="^(|clear|caution|suspicious|dangerous)$"),
) -> ScanListResponse:
    page_size = get_settings().dashboard_page_size
    offset = (page - 1) * page_size
    try:
        with session_scope() as session:
            _require_db(session)
            total = session.execute(
                text("SELECT count(*) FROM scans "
                     "WHERE (:severity = '' OR severity = :severity)"),
                {"severity": severity},
            ).scalar_one()
            rows = session.execute(
                text(_SCAN_ROWS),
                {"severity": severity, "limit": page_size, "offset": offset},
            ).all()
    except HTTPException:
        raise
    except Exception as exc:
        log.exception("dashboard scan listing failed")
        raise unavailable("dashboard unavailable: database unreachable") from exc

    scans = [
        ScanSummary(
            scan_id=r[0],
            scored_at=_iso(r[1]),
            risk_score=r[2],
            severity=r[3],
            duration_ms=r[4],
            install_id_short=str(r[5])[:8] if r[5] else None,
            model_variant=r[6],
            top_signal=r[7],
            has_feedback=bool(r[8]),
        )
        for r in rows
    ]
    return ScanListResponse(scans=scans, total=total, page=page, page_size=page_size)


# ------------------------------------------------------- feedback review --

_FEEDBACK_ROWS = """
    SELECT f.feedback_id, f.scan_id, f.disagreement, f.note,
           f.created_at, f.reviewed_at, s.severity, s.risk_score
      FROM feedback f
      LEFT JOIN scans s ON s.scan_id = f.scan_id
     WHERE (:only_unreviewed = false OR f.reviewed_at IS NULL)
     ORDER BY f.reviewed_at IS NULL DESC, f.created_at DESC
     LIMIT 200
"""


@router.get("/feedback", response_model=FeedbackListResponse, dependencies=_GUARD)
def list_feedback(
    unreviewed_only: bool = Query(default=False),
) -> FeedbackListResponse:
    try:
        with session_scope() as session:
            _require_db(session)
            rows = session.execute(
                text(_FEEDBACK_ROWS), {"only_unreviewed": unreviewed_only}).all()
            total, unreviewed = session.execute(
                text("SELECT count(*), count(*) FILTER (WHERE reviewed_at IS NULL) "
                     "FROM feedback")).one()
    except HTTPException:
        raise
    except Exception as exc:
        log.exception("dashboard feedback listing failed")
        raise unavailable("dashboard unavailable: database unreachable") from exc

    items = [
        FeedbackItem(
            feedback_id=r[0], scan_id=r[1], disagreement=r[2], note=r[3],
            created_at=_iso(r[4]), reviewed_at=_iso(r[5]),
            scan_severity=r[6], scan_risk_score=r[7],
        )
        for r in rows
    ]
    return FeedbackListResponse(feedback=items, total=total, unreviewed=unreviewed)


@router.post("/feedback/{feedback_id}/review", response_model=FeedbackItem,
             dependencies=_GUARD)
def mark_reviewed(feedback_id: int) -> FeedbackItem:
    """Stamp reviewed_at. This is the human step WBS 2.4 depends on.

    Marking a row reviewed records that a person looked at it. It does not
    relabel the scan, retrain anything, or feed the model - feedback is a queue
    for calibration work, never ground truth applied automatically
    (00_Admin/auth-design-revision.md).
    """
    try:
        with session_scope() as session:
            _require_db(session)
            row = session.execute(
                text("""
                    UPDATE feedback
                       SET reviewed_at = COALESCE(reviewed_at, now())
                     WHERE feedback_id = :f
                 RETURNING feedback_id, scan_id, disagreement, note,
                           created_at, reviewed_at
                """),
                {"f": feedback_id},
            ).first()
            if row is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "no such feedback")
    except HTTPException:
        raise
    except Exception as exc:
        log.exception("marking feedback reviewed failed")
        raise unavailable("dashboard unavailable: database unreachable") from exc

    return FeedbackItem(
        feedback_id=row[0], scan_id=row[1], disagreement=row[2], note=row[3],
        created_at=_iso(row[4]), reviewed_at=_iso(row[5]),
    )


# ---------------------------------------------------------------- metrics --

_METRICS = """
    SELECT
      (SELECT count(*) FROM scans)                                        AS total_scans,
      (SELECT count(*) FROM scans WHERE scored_at > now() - interval '7 days')
                                                                          AS last_7,
      (SELECT percentile_disc(0.5) WITHIN GROUP (ORDER BY duration_ms)
         FROM scans WHERE duration_ms IS NOT NULL)                        AS median_ms,
      (SELECT count(*) FROM installs WHERE revoked_at IS NULL)            AS installs,
      (SELECT count(*) FROM feedback)                                     AS fb_total,
      (SELECT count(*) FROM feedback WHERE reviewed_at IS NULL)           AS fb_unreviewed,
      (SELECT count(*) FROM feedback WHERE disagreement = 'false_positive') AS fb_fp,
      (SELECT count(*) FROM feedback WHERE disagreement = 'false_negative') AS fb_fn,
      (SELECT variant FROM model_versions WHERE is_active LIMIT 1)        AS variant,
      (SELECT trained_utc FROM model_versions WHERE is_active LIMIT 1)    AS trained
"""


@router.get("/metrics", response_model=MetricsResponse, dependencies=_GUARD)
def metrics() -> MetricsResponse:
    try:
        with session_scope() as session:
            _require_db(session)
            m = session.execute(text(_METRICS)).one()
            by_severity = session.execute(
                text("SELECT severity, count(*) FROM scans "
                     "GROUP BY severity ORDER BY count(*) DESC")).all()
    except HTTPException:
        raise
    except Exception as exc:
        log.exception("dashboard metrics failed")
        raise unavailable("dashboard unavailable: database unreachable") from exc

    total_scans = m[0] or 0
    fb_total = m[4] or 0
    return MetricsResponse(
        total_scans=total_scans,
        scans_by_severity=[SeverityCount(severity=r[0], count=r[1]) for r in by_severity],
        scans_last_7_days=m[1] or 0,
        median_duration_ms=int(m[2]) if m[2] is not None else None,
        active_installs=m[3] or 0,
        total_feedback=fb_total,
        unreviewed_feedback=m[5] or 0,
        reported_false_positives=m[6] or 0,
        reported_false_negatives=m[7] or 0,
        reported_disagreement_rate=round(fb_total / total_scans, 4) if total_scans else 0.0,
        active_model_variant=m[8],
        active_model_trained_utc=_iso(m[9]),
    )
