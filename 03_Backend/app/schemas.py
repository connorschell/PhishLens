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


class HealthResponse(BaseModel):
    status: str
    version: str
    model_loaded: bool
    model_variant: str | None = None
    model_trained_utc: str | None = None
    database: str
