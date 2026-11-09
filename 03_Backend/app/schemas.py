"""WBS 3.3 - request and response shapes.

Every inbound field is bounded. The extension is a client the server does not
control, so the server validates rather than trusts (A-02, payload bounds).
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from .config import get_settings

_s = get_settings()


class AttachmentIn(BaseModel):
    filename: str = Field(default="", max_length=400)
    content_type: str = Field(default="", max_length=200)
    size_bytes: int = Field(default=0, ge=0, le=5_000_000_000)


class ScanRequest(BaseModel):
    """What the content script scrapes from the rendered Gmail page (WBS 4.2)."""

    from_display: str = Field(default="", max_length=400)
    from_address: str = Field(default="", max_length=320)
    reply_to_address: str = Field(default="", max_length=320)
    subject: str = Field(default="", max_length=_s.max_subject_chars)
    body_text: str = Field(default="", max_length=_s.max_body_text_chars)
    body_html: str = Field(default="", max_length=_s.max_body_html_chars)
    attachments: list[AttachmentIn] = Field(default_factory=list,
                                            max_length=_s.max_attachments)


class SignalOut(BaseModel):
    kind: str                      # "model" or "rule"
    text: str
    feature: str | None = None
    rule: str | None = None
    share: float | None = None


class MitigatingOut(BaseModel):
    feature: str
    text: str


class ScanResponse(BaseModel):
    scan_id: int | None = Field(
        default=None,
        description="Null when the scan could not be recorded; the verdict is unaffected.")
    risk_score: int
    severity: str
    headline: str
    advice: str
    signals: list[SignalOut]
    mitigating: list[MitigatingOut]
    model_variant: str
    signals_considered: int
    persisted: bool
    duration_ms: int
    model_severity: str = Field(
        description="The tier the model alone produced, before any rule floor (WBS 2.3).")
    severity_floored_by: str | None = Field(
        default=None,
        description="Name of the deterministic rule that raised the tier, or null if none did.")


class HealthResponse(BaseModel):
    status: str
    version: str
    model_loaded: bool
    model_variant: str | None = None
    model_trained_utc: str | None = None
    database: str


# --------------------------------------------------------------- WBS 3.4 --

class RegisterRequest(BaseModel):
    """First-run call from the extension's service worker (A-02)."""

    extension_version: str = Field(default="0.0.0", max_length=50)
    client_platform: str = Field(default="chrome", max_length=30)


class RegisterResponse(BaseModel):
    install_id: str
    token: str = Field(description="Returned once and never again; only its hash is stored.")
    issued_at: str


class FeedbackRequest(BaseModel):
    """A user disagreeing with a verdict (WBS 4.4 control posts this)."""

    scan_id: int = Field(ge=1)
    disagreement: str = Field(pattern="^(false_positive|false_negative)$")
    note: str | None = Field(default=None, max_length=_s.max_feedback_note_chars)


class FeedbackResponse(BaseModel):
    feedback_id: int
    scan_id: int
    disagreement: str
    recorded_at: str
    note_stored: bool
