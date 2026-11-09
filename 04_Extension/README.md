# PhishLens extension (WBS 4)

Chrome Manifest V3. Reads the open Gmail message from the page DOM, sends it to
the PhishLens API, and shows the score, the severity tier and the ranked
explanation.

## What exists (WBS 4.1)

| File | Role |
|---|---|
| `manifest.json` | MV3 manifest: storage permission, one host permission, content script on `mail.google.com` |
| `config.js` | API base URL, storage keys, timeouts and backoff — the only file with constants in it |
| `background/service_worker.js` | Registration, token custody, and every call to the API |
| `content/gmail.js` | Notices the open message, mounts a shadow-root host for the panel, tears it down on navigation |
| `content/panel.css` | Mount-point layout only; the panel is styled inside its shadow root |

## What is stubbed

- **WBS 4.2** — Gmail DOM parsing and payload assembly. `content/gmail.js`
  mounts and sets `data-phishlens-state="awaiting-4.2"`; it reads nothing.
- **WBS 4.3** — the panel UI. Mockups: `06_Deliverables/gui/mockups/`.
- **WBS 4.4** — the feedback control. The worker already routes `FEEDBACK`.

## Before it can run

`API_BASE` in `config.js` is `https://api.phishlens.invalid`. `.invalid` can
never resolve, so an unconfigured build fails loudly instead of silently
pointing somewhere wrong. Two things change together once the domain exists
(A-17 item 3):

1. `API_BASE` in `config.js`
2. `host_permissions` in `manifest.json`

They must match, or Chrome blocks the request regardless of what the code says.

## Loading it

1. `chrome://extensions` → enable **Developer mode**
2. **Load unpacked** → select `04_Extension/`
3. Open `chrome://extensions` → PhishLens → **service worker** for its console
4. Open Gmail and a message; `document.getElementById("phishlens-panel-host")`
   should exist in the page

## Token handling

The token never reaches the content script. The content script posts a message,
the service worker attaches `Authorization: Bearer`, and only the panel data
comes back. The token sits in `chrome.storage.local`, which is scoped to the
extension origin — Gmail's page scripts cannot read it.

See `03_Backend/API_CONTRACT.md` for the endpoints and the status codes this
client has to handle.
