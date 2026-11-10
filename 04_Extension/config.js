/**
 * WBS 4.1 - build constants.
 *
 * The hostname exists as of 11/10: api.usephishlens.app, behind Nginx with a
 * Let's Encrypt certificate (WBS 5.2). API_BASE and the host_permissions entry
 * in manifest.json must always name the same origin.
 *
 * The droplet's bare IP was never an option: Let's Encrypt will not issue for
 * an IP address, and the extension must not talk to the API over plain HTTP.
 */

/**
 * Where the API lives.
 *
 * Points at the deployed server as of 11/10. host_permissions in manifest.json
 * still lists http://localhost:8000 as well, so falling back to a local stack
 * is a one-line change here and needs no manifest edit - which matters if the
 * droplet or the network is unavailable during a demo.
 *
 * Chrome treats http://localhost as a trustworthy origin, so the local option
 * works with no certificate. Any other plain-HTTP origin would be blocked, and
 * should be.
 */
/** The deployed API: Nginx + Let's Encrypt on the droplet (WBS 5.2). */
export const API_BASE_DEPLOYED = "https://api.usephishlens.app";

/** The local stack, for development and as a demo fallback. */
export const API_BASE_LOCAL = "http://localhost:8000";

/** Declared after both, not before: `const` is not hoisted, so naming
 *  API_BASE_DEPLOYED above this line would throw at module load. */
export const API_BASE = API_BASE_DEPLOYED;

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
