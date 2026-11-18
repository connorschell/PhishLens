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

    # Key for the per-install token scheme and the dashboard session MAC. Empty
    # or left at the template placeholder disables the dashboard (app/
    # admin_auth.py) rather than signing sessions with a known value.
    token_signing_secret: str = ""

    # --- WBS 3.5: Google Safe Browsing -------------------------------------
    # Blank key means the signal is simply not used: no error, no warning on
    # every scan, the verdict falls back to the model and the existing rules.
    safe_browsing_api_key: str = ""
    safe_browsing_enabled: bool = True
    # Short on purpose. Someone is waiting on a security decision, so a slow
    # warning is a worse failure than a missing third-party signal.
    safe_browsing_timeout_s: float = 2.0
    # Bounds one message's upstream request and cache writes.
    safe_browsing_max_urls: int = 10
    # Google returns cacheDuration for a match; this is the fallback. The safe
    # TTL is ours entirely - the API reports only matches, so "no match" has no
    # duration attached, and a clean URL can turn malicious later.
    safe_browsing_unsafe_ttl_s: int = 300
    safe_browsing_safe_ttl_s: int = 43_200          # 12 hours

    # --- WBS 4.5: operator dashboard ---------------------------------------
    # Single operator password. Empty means the dashboard cannot issue a
    # session and every route under it returns 503. Fail-closed on purpose: an
    # unconfigured dashboard that refuses to work is a visible problem, an
    # unconfigured dashboard serving scan history to anyone is not.
    dashboard_password: str = ""
    dashboard_session_hours: int = 12
    # Per IP. Strict, because this is the only endpoint that takes a password.
    dashboard_login_rate_limit: str = "10/hour"
    # Page size cap for the history view; bounds the response and the query.
    dashboard_page_size: int = 50

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
