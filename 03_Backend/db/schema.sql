-- PhishLens database schema -- WBS 3.1
--
-- PostgreSQL 16. This file is the readable reference for the schema; the
-- numbered files in migrations/ are what actually create it, and Compose runs
-- them on first start of the database volume.
--
-- PRIVACY DECISION (recorded here because the schema is where it binds):
-- no raw message content is stored. The extension sends the message so the
-- server can run the one parser shared with training (see 00_Admin/
-- data-handling.md for why the alternative was rejected), but what lands in
-- this database is the measurements, the score and the explanation -- never the
-- subject, body or sender address. A scan is identified by a salted hash so a
-- re-scan of the same message can be recognised without storing the message.

BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ---------------------------------------------------------------- installs --
-- One row per extension installation. The token is an identifier, not a
-- secret (00_Admin/auth-design-revision.md, grader item A-02): it is stored
-- hashed, it can be revoked individually, and it is what makes per-install
-- rate limiting and feedback attribution possible. Issued by /register in
-- WBS 3.4.
CREATE TABLE installs (
    install_id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    token_hash         bytea NOT NULL UNIQUE,
    extension_version  text  NOT NULL,
    client_platform    text  NOT NULL DEFAULT 'chrome',
    created_at         timestamptz NOT NULL DEFAULT now(),
    last_seen_at       timestamptz,
    revoked_at         timestamptz,
    CONSTRAINT installs_token_hash_len CHECK (octet_length(token_hash) = 32)
);

CREATE INDEX installs_active_idx ON installs (install_id) WHERE revoked_at IS NULL;

-- ---------------------------------------------------------- model_versions --
-- Every scan records which model produced it. Without this, a result in the
-- dashboard three weeks from now cannot be attributed to the model that made
-- it, and the WBS 2.1 full-versus-ablated comparison becomes unreportable.
CREATE TABLE model_versions (
    model_version_id serial PRIMARY KEY,
    variant          text NOT NULL CHECK (variant IN ('full', 'ablated')),
    trained_utc      timestamptz NOT NULL,
    n_features       integer NOT NULL CHECK (n_features > 0),
    n_train          integer NOT NULL CHECK (n_train > 0),
    bundle_sha256    bytea NOT NULL UNIQUE,
    severity_tiers   jsonb NOT NULL,
    is_active        boolean NOT NULL DEFAULT false,
    loaded_at        timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT model_versions_tiers_shape CHECK (
        severity_tiers ? 'caution' AND severity_tiers ? 'suspicious'
        AND severity_tiers ? 'dangerous')
);

-- Exactly one active model at a time.
CREATE UNIQUE INDEX model_versions_one_active_idx
    ON model_versions ((is_active)) WHERE is_active;

-- ------------------------------------------------------------------- scans --
-- One row per scored message. No message content: message_fingerprint is a
-- salted SHA-256 over the normalized subject and body, computed server side
-- and never reversible to the message.
CREATE TABLE scans (
    scan_id             bigserial PRIMARY KEY,
    install_id          uuid REFERENCES installs (install_id) ON DELETE SET NULL,
    model_version_id    integer NOT NULL REFERENCES model_versions (model_version_id),
    message_fingerprint bytea NOT NULL,
    risk_score          smallint NOT NULL CHECK (risk_score BETWEEN 0 AND 100),
    probability         double precision NOT NULL CHECK (probability BETWEEN 0 AND 1),
    severity            text NOT NULL CHECK (severity IN ('clear','caution','suspicious','dangerous')),
    features            jsonb NOT NULL,      -- the 43 measurements, by name
    scored_at           timestamptz NOT NULL DEFAULT now(),
    duration_ms         integer CHECK (duration_ms >= 0),
    CONSTRAINT scans_fingerprint_len CHECK (octet_length(message_fingerprint) = 32)
);

CREATE INDEX scans_install_time_idx ON scans (install_id, scored_at DESC);
CREATE INDEX scans_fingerprint_idx   ON scans (message_fingerprint);
CREATE INDEX scans_severity_idx      ON scans (severity, scored_at DESC);

-- -------------------------------------------------------------- indicators --
-- The explanation, one row per signal shown to the user. Stored rather than
-- recomputed because the explanation a user acted on must stay reproducible
-- even after the model is retrained.
CREATE TABLE indicators (
    indicator_id bigserial PRIMARY KEY,
    scan_id      bigint NOT NULL REFERENCES scans (scan_id) ON DELETE CASCADE,
    rank         smallint NOT NULL CHECK (rank >= 0),
    kind         text NOT NULL CHECK (kind IN ('model', 'rule')),
    feature      text,                       -- null for rule-layer signals
    rule         text,                       -- null for model-layer signals
    display_text text NOT NULL,
    share        real CHECK (share BETWEEN 0 AND 1),
    contribution double precision,
    CONSTRAINT indicators_kind_fields CHECK (
        (kind = 'model' AND feature IS NOT NULL) OR
        (kind = 'rule'  AND rule    IS NOT NULL))
);

CREATE INDEX indicators_scan_idx    ON indicators (scan_id, rank);
CREATE INDEX indicators_feature_idx ON indicators (feature) WHERE feature IS NOT NULL;

-- --------------------------------------------------------- url_reputation --
-- Cache for Google Safe Browsing (WBS 3.5). Holds a hash of the URL, not the
-- URL: a cache of the addresses users received is a privacy liability and the
-- lookup only needs equality. expires_at drives graceful degradation -- a stale
-- or missing row means the signal is simply not used for that scan.
CREATE TABLE url_reputation (
    url_sha256  bytea PRIMARY KEY,
    verdict     text NOT NULL CHECK (verdict IN ('safe','unsafe','unknown')),
    threat_type text,
    source      text NOT NULL DEFAULT 'google_safe_browsing',
    checked_at  timestamptz NOT NULL DEFAULT now(),
    expires_at  timestamptz NOT NULL,
    CONSTRAINT url_reputation_hash_len CHECK (octet_length(url_sha256) = 32),
    CONSTRAINT url_reputation_window   CHECK (expires_at > checked_at)
);

CREATE INDEX url_reputation_expiry_idx ON url_reputation (expires_at);

-- ---------------------------------------------------------------- feedback --
-- User disagreement with a verdict (WBS 3.4 endpoint, WBS 4.4 control).
-- Feedback is a signal to review, never ground truth applied automatically --
-- see the auth design note on poisoning.
CREATE TABLE feedback (
    feedback_id  bigserial PRIMARY KEY,
    scan_id      bigint NOT NULL REFERENCES scans (scan_id) ON DELETE CASCADE,
    install_id   uuid REFERENCES installs (install_id) ON DELETE SET NULL,
    disagreement text NOT NULL CHECK (disagreement IN ('false_positive','false_negative')),
    note         text CHECK (note IS NULL OR length(note) <= 500),
    created_at   timestamptz NOT NULL DEFAULT now(),
    reviewed_at  timestamptz,
    CONSTRAINT feedback_one_per_install_per_scan UNIQUE (scan_id, install_id)
);

CREATE INDEX feedback_unreviewed_idx ON feedback (created_at) WHERE reviewed_at IS NULL;

COMMIT;
