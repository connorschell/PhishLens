# IM2 runbook

**Due Wednesday 11 November, 10:45 AM. Deck on Scholar by 8:00 AM that day.**
7 minutes, hard cut. Everything below is the part I cannot do for you.

---

## 1. Set up the demo machine (do this first, not on the day)

The demo runs against the **deployed** server at `https://api.usephishlens.app`,
which went live 11/10. You do not need Docker running locally for it.

```powershell
curl.exe -sS https://api.usephishlens.app/health
```

Expect `"version":"0.3.0"` and `"model_loaded":true`. If that fails, fall back to
local (see *If the server is down* below) rather than debugging on the day.

Then load the extension:

```
chrome://extensions  ->  Developer mode ON  ->  Load unpacked  ->  04_Extension
```

**Order matters.** Load the extension *before* opening Gmail. Reloading the
extension under a Gmail tab that is already open kills the injected script, and
the panel then hangs on its loading state with no way out. If that happens,
refresh the Gmail tab.

### If the server is down

In `04_Extension/config.js`, change the last line of the API block to:

```js
export const API_BASE = API_BASE_LOCAL;
```

Then `docker compose up -d` locally, reload the extension, reopen Gmail. Chrome
trusts `http://localhost` without a certificate, so this works with no setup.
Say out loud that you are demoing against a local instance and why — having a
tested fallback is not a failure.

Open the service worker console from that same page (click **service worker**
under PhishLens). On first run it should log `registered install <uuid>`. If it
logs a registration error instead, the stack is not up — fix that before going
further.

## 2. Verify it actually scans (the step that decides the grade)

1. Open Gmail in the same Chrome profile.
2. Open any message. Within about a second the PhishLens panel should appear
   above the message body.
3. Open a real phishing email, or send yourself the test message below from
   another address.

If the panel says **"Couldn't read this message"**, the Gmail selectors in
`04_Extension/content/parse.js` need adjusting — tell me and I'll fix them. That
file is the only place they live. **Check this by Sunday**, not Tuesday night.

### Test message to send yourself

> **Subject:** Your account verification has not yet been completed
>
> Dear Users, We are reaching out about an essential security update regarding
> your Wallet. Verify your account now or it will be suspended. Confirm your
> password at the link below.
>
> https://www.ledger.com/wallet/device-verify
> *(make the link actually point somewhere else, e.g. example.com — that
> mismatch is what the rule layer catches)*

You also need a **legitimate** message to show the CLEAR tier. Any normal email
from a person works.

## 3. Record the backup video (optional — see note)

> Not an IM2 requirement. The recorded demonstration is deliverable #22, due with
> the **final** presentation on 11/30. It is insurance for tomorrow, not a
> graded item. Skip it if time is short.


Do this once the demo works, and before Tuesday. Windows + Alt + R starts the Xbox
Game Bar recorder; OBS is better if you have it.

Record 90 seconds: phishing message → panel appears → legitimate message →
CLEAR. Save it as `06_Deliverables/backup_demo.mp4` (that's deliverable #22 in
the tracker, so this does double duty).

**If anything fails during the live demo, switch to the video immediately.** Do
not debug in front of the class.

## 4. Commit and push

The assignment requires a git repo link with a README. The README is updated and
ready; nothing from the last week is committed yet.

```powershell
git add -A
git commit -m "WBS 3.4 auth and rate limiting, WBS 4.1-4.3 extension, A-19 mockups"
./push.sh
```

Then open `https://github.com/connorschell/PhishLens` in a browser and confirm
the README renders and the commit is there. **If the repo is private, the
professor cannot see it** — either make it public or add him as a collaborator.

## 5. Submit to Scholar by 8:00 AM Wednesday

Two things, per the assignment:

- `06_Deliverables/IM2_Presentation.pptx`
- The GitHub repo link

## 6. Rehearse

Once, out loud, with a timer. The presentation is cut at 7 minutes.

Budget:

| | |
|---|---|
| Intro (slide 2) | 30s |
| Background (slides 3–4) | 80s |
| **Demo (slide 5)** | **3m 30s** |
| How it works (slide 6) | 45s |
| Evidence (slide 7) | 30s |
| Resolved + next (slides 8–9) | 60s |

Every slide has speaker notes already written — open the deck in Presenter View
and they're there.

The demo is the part that runs long. Practise that bit specifically: open
message, let the panel load, read the top signal out loud, open the clean one,
done. Resist narrating every signal — read the top one and point at the rest.

## 7. On the day

- Dress at least business casual. It's a graded line item.
- Confirm `https://api.usephishlens.app/health` answers **before** class.
- Load the extension, **then** open Gmail — not the other way round.
- Have Gmail already open with both test messages visible in the list.
- Have the backup video open in a second tab, ready to play.
- Close Slack, email notifications, and anything else that pops up.

---

## What to say if asked

**"Why not just use the IP address for the demo server?"**
Let's Encrypt won't issue a certificate for a bare IP — certificates are issued
to names, not numbers. That was the blocker reported at the last update. It's
resolved: `api.usephishlens.app` was registered 11/10 and the demo you just
watched ran against it over HTTPS.

**"Is the token secure?"**
It's an identifier, not a secret. Anyone can register and get one. What it buys
is isolation and revocability — I can rate-limit or cut off one install without
affecting any other. A Chrome extension can't hold a real secret because its
files sit on the user's disk.

**"What are your precision and recall?"**
Those come from the held-out evaluation in the final weeks. Quoting numbers now
would be quoting training-set performance. I report precision, recall and
false-positive rate, never accuracy, because the corpus is unbalanced enough
that accuracy would flatter the model.

**"What happens if your server goes down?"**
The panel says it can't check the message and tells the user what to look at
themselves. It never implies the message is safe. If only the database is down,
scanning still works and just doesn't record — a warning withheld during an
outage is the worse failure.

**"Did you write this yourself?"**
Answer honestly: you used Claude as a coding collaborator, which the course
permits, and you can explain every design decision in the system. Then
demonstrate that by explaining one. Re-read `09_Reference/week6_explained_audio.txt`
and `00_Admin/auth-design-revision.md` before Wednesday so that's true.
