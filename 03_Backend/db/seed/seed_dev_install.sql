-- WBS 3.2 - a development install row, so /scan can be exercised before
-- /register exists (that endpoint lands in WBS 3.4).
--
-- The token this corresponds to is 'pl_dev_localonly'. It is a development
-- fixture, it is committed deliberately, and it is useless against any
-- deployment because the real /register mints 32 random bytes per install.

INSERT INTO installs (install_id, token_hash, extension_version, client_platform)
VALUES (
    '00000000-0000-4000-8000-000000000001',
    digest('pl_dev_localonly', 'sha256'),
    '0.0.0-dev',
    'chrome'
)
ON CONFLICT (token_hash) DO NOTHING;
