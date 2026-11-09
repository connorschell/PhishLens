"""WBS 3.4 - POST /feedback.

A user telling the system it got a verdict wrong. Three rules shape this
endpoint, all of them from the approved design:

1. Feedback must be attributable, so authentication is required here with no
   degraded path. Unattributable feedback cannot be rate limited, weighted or
   isolated if it turns out to be poisoned, which makes it worthless as a
   review signal (00_Admin/auth-design-revision.md).
2. A caller may only leave feedback on its own scans. Without that check the
   endpoint is an oracle for probing which scan ids exist and what they were.
3. Feedback is recorded for review, never applied to the model automatically.
   The row lands with reviewed_at NULL and nothing downstream reads it until a
   human does (WBS 2.4 calibration).
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from ..auth import Revoked, authorization_header, bearer_token, resolve_install, unauthorized
from ..db import session_scope
from ..ratelimit import feedback_limit
from ..schemas import FeedbackRequest, FeedbackResponse

log = logging.getLogger(__name__)
router = APIRouter(tags=["feedback"])


@router.post("/feedback", response_model=FeedbackResponse,
             status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(feedback_limit)])
def submit_feedback(
    req: FeedbackRequest,
    authorization: str | None = Depends(authorization_header),
) -> FeedbackResponse:
    token = bearer_token(authorization)
    if not token:
        raise unauthorized("feedback requires a per-install token; call /register first")

    try:
        with session_scope() as session:
            if session is None:
                raise HTTPException(
                    status.HTTP_503_SERVICE_UNAVAILABLE,
                    "feedback unavailable: no database configured")

            try:
                install = resolve_install(session, token)
            except Revoked as exc:
                raise unauthorized("this install has been revoked") from exc
            if install is None:
                raise unauthorized("unrecognised install token")

            owner = session.execute(
                text("SELECT install_id FROM scans WHERE scan_id = :s"),
                {"s": req.scan_id},
            ).first()
            if owner is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "no such scan")
            # Rule 2. A null owner is a scan recorded in the degraded path; it
            # belongs to nobody and cannot be claimed after the fact.
            if owner[0] is None or str(owner[0]) != install.install_id:
                raise HTTPException(
                    status.HTTP_403_FORBIDDEN,
                    "that scan belongs to another install")

            try:
                row = session.execute(
                    text("""
                        INSERT INTO feedback (scan_id, install_id, disagreement, note)
                        VALUES (:s, :i, :d, :n)
                        RETURNING feedback_id, created_at
                    """),
                    {"s": req.scan_id, "i": install.install_id,
                     "d": req.disagreement, "n": req.note},
                ).first()
            except IntegrityError as exc:
                raise HTTPException(
                    status.HTTP_409_CONFLICT,
                    "this install has already left feedback on that scan") from exc

            feedback_id, created_at = row[0], row[1]
    except HTTPException:
        raise
    except Exception as exc:
        log.exception("feedback not recorded")
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "feedback unavailable: database unreachable") from exc

    return FeedbackResponse(
        feedback_id=feedback_id,
        scan_id=req.scan_id,
        disagreement=req.disagreement,
        recorded_at=created_at.isoformat(),
        note_stored=bool(req.note),
    )
