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


@lru_cache
def get_settings() -> Settings:
    return Settings()
