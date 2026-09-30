"""WBS 1.1 - the common record schema every corpus is normalized into.

One dataclass, one JSON object per message, one JSON Lines file per split.
Everything downstream - the feature extractor (1.4), the training set (1.5), and
the extension payload the API receives (4.2) - speaks this schema, so a message
scraped live out of the Gmail DOM and a message read from a corpus file reach the
model in the same shape.

Fields that Gmail's rendered DOM cannot supply are marked AVAILABILITY: corpus-only.
They are kept because they are useful for error analysis and for quantifying what
the DOM-parsing limitation costs us, but the model must not train on them.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

SCHEMA_VERSION = "1.0"

LABELS = ("phish", "spam", "ham")


@dataclass
class Link:
    """One hyperlink found in the message body."""

    url: str
    host: str
    registered_domain: str
    scheme: str
    display_text: str = ""
    in_html: bool = True
    display_mismatch: bool = False  # anchor text names a different domain than href


@dataclass
class Attachment:
    filename: str
    content_type: str
    size_bytes: int


@dataclass
class EmailRecord:
    """A single normalized message."""

    # --- identity and provenance ---
    record_id: str  # sha256 of the raw message, truncated
    source_corpus: str  # spamassassin | phishing_pot | gmail_dom
    source_group: str  # easy-ham-1, spam-2, email, ...
    source_path: str  # path within the corpus, for traceability
    label: str  # phish | spam | ham
    schema_version: str = SCHEMA_VERSION

    # --- sender ---
    from_display: str = ""
    from_address: str = ""
    from_domain: str = ""
    from_registered_domain: str = ""
    reply_to_address: str = ""
    reply_to_domain: str = ""
    return_path_address: str = ""  # AVAILABILITY: corpus-only
    sender_mismatch: bool = False  # From vs Reply-To or Return-Path disagree

    # --- envelope ---
    to_address: str = ""
    subject: str = ""
    date_raw: str = ""
    date_iso: str = ""
    message_id: str = ""
    received_count: int = 0  # AVAILABILITY: corpus-only
    auth_results_present: bool = False  # AVAILABILITY: corpus-only (SPF/DKIM/DMARC)
    list_unsubscribe_present: bool = False

    # --- body ---
    body_text: str = ""  # plain text, HTML stripped if that was all there was
    has_html_part: bool = False
    has_text_part: bool = False
    body_char_count: int = 0
    body_word_count: int = 0

    # --- structure ---
    links: list[Link] = field(default_factory=list)
    link_count: int = 0
    distinct_link_domains: int = 0
    display_mismatch_count: int = 0
    attachments: list[Attachment] = field(default_factory=list)
    attachment_count: int = 0

    # --- parse health ---
    parse_warnings: list[str] = field(default_factory=list)

    def to_json_dict(self) -> dict[str, Any]:
        return asdict(self)
