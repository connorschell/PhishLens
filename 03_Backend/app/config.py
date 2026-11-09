"""WBS 3.3 - settings, read from the environment."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = ""
    api_env: str = "development"
    log_level: str = "INFO"

    # Model bundle to score with. The database records which version produced
    # each scan; this chooses which one the process loads.
    model_variant: str = "full"

    # Salt for the message fingerprint. Without it the fingerprint is a plain
    # hash of the message and a dictionary attack over common subjects would
    # recover them, which would undo the point of not storing content.
    fingerprint_salt: str = "change_me_locally"

    # Payload bounds. Generous enough for real mail, small enough that a single
    # request cannot be used to exhaust memory (00_Admin/auth-design-revision.md).
    max_subject_chars: int = 998
    max_body_text_chars: int = 200_000
    max_body_html_chars: int = 500_000
    max_attachments: int = 25

    # --- WBS 3.4: authentication and rate limiting -------------------------
    # Enforce per-install tokens on /scan. On by default: a deployment that
    # silently accepted anonymous scans because a flag was unset would defeat
    # the point of A-02. The degraded path (token store unreachable) is handled
    # in app/auth.py and is a deliberate, documented trade, not this switch.
    require_auth: bool = True

    # Accepted extension origins for CORS. Empty means same-origin only, which
    # is what the local test page uses. The published extension id goes here in
    # the deployed .env as chrome-extension://<id> (WBS 4.1).
    allowed_origins: list[str] = []

    rate_limit_enabled: bool = True
    # Per install. Generous: a user reading mail quickly should never see a 429.
    scan_rate_limit: str = "60/minute"
    # Per IP. Strict: this is the endpoint that mints identities.
    register_rate_limit: str = "10/hour"
    # Per install. Feedback is a review signal; nobody legitimately submits more.
    feedback_rate_limit: str = "20/hour"
    # Free-text note length on feedback, mirrored by the schema CHECK.
    max_feedback_note_chars: int = 500


@lru_cache
def get_settings() -> Settings:
    return Settings()
