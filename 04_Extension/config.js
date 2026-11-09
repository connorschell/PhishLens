/**
 * WBS 4.1 - build constants.
 *
 * API_BASE is deliberately a .invalid hostname. That TLD can never resolve, so
 * a build that was never pointed at the real API fails loudly in development
 * instead of quietly shipping a broken or wrong host. Claiming the domain is
 * A-17 item 3; when it exists, this constant and the host_permissions entry in
 * manifest.json are the only two places that change, and they must match.
 *
 * The droplet's bare IP is not an option: Let's Encrypt will not issue for an
 * IP address, and the extension must not talk to the API over plain HTTP.
 */

/**
 * Where the API lives.
 *
 * localhost is deliberate for the IM2 demo, and it is not a shortcut around
 * TLS. Chrome treats http://localhost as a trustworthy origin - it is the one
 * plain-HTTP address that is not downgraded - because nothing leaves the
 * machine. So the extension can talk to a locally running stack with no
 * certificate at all, while the deployed server still requires HTTPS and
 * still needs the hostname that WBS 5.2 is blocked on.
 *
 * Swap API_BASE to the deployed hostname once it exists. host_permissions in
 * manifest.json lists both; the unused one costs nothing and keeps the switch
 * to one line here.
 */
export const API_BASE = "http://localhost:8000";

/** The deployed address, once WBS 5.2 is unblocked (A-17 item 3). */
export const API_BASE_DEPLOYED = "https://api.phishlens.invalid";

export const HOSTNAME_PENDING = API_BASE.endsWith(".invalid");

/** True when pointed at a local stack rather than a deployed one. */
export const LOCAL_MODE = API_BASE.startsWith("http://localhost");

/** Extension version, read from the manifest so the two cannot drift. */
export const EXTENSION_VERSION = chrome.runtime.getManifest().version;

export const CLIENT_PLATFORM = "chrome";

/** Where the per-install token lives. Extension-origin storage: page scripts
 *  on mail.google.com cannot read it, and neither can the content script. */
export const TOKEN_KEY = "phishlens_install_token";
export const INSTALL_ID_KEY = "phishlens_install_id";

/** Registration backoff. /register is rate limited to 10/hour per IP, so a
 *  client that retries tightly would lock itself out of the endpoint it needs. */
export const REGISTER_BACKOFF_MS = [2_000, 15_000, 60_000, 300_000];

/** Scan requests are abandoned rather than queued: a verdict that arrives after
 *  the user has moved to another message is noise, not help. */
export const SCAN_TIMEOUT_MS = 8_000;
