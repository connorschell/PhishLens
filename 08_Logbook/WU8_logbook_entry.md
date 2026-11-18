# Week 8 logbook entry — week ending 18 November 2026

PhishLens · CYBR 498W · Connor Schell

## Hours

7.5 hours against 17.5 estimated. Two of the three tasks came in well under:
the dashboard because the database schema from WBS 3.1 already held everything
it needed to display, and Safe Browsing because the Lookup API is a single
request and the cache table was built for it in week 5. Running total 95.25.

| Task | Hours | What was done |
|---|---|---|
| 4.5 | 3.0 | Operator dashboard — read endpoints, password gate, three views |
| 4.5 | 1.0 | Deployed to the VPS; SSH set up from the replacement laptop |
| 3.5 | 2.5 | Google Safe Browsing — cached rule-layer signal with graceful degradation |
| 4.6 | 1.0 | Fixed the panel hang on an invalidated extension context |

## What was completed

**WBS 4.5, the operator dashboard.** The system had been write-only: scans and
feedback went into the database and nothing read them back. The dashboard adds
four endpoints — paged scan history with a severity filter, the feedback queue,
a mark-as-reviewed write, and aggregate counts — plus the page that consumes
them.

The decision worth recording is the credential. The obvious move was to reuse
the per-install token from WBS 3.4, and it is wrong: that token is deliberately
scoped to one install's own rows and lives in `chrome.storage.local` on an
ordinary user's machine. Giving it authority over everyone else's history would
undo precisely the isolation the A-02 design was built to provide. So the
dashboard has its own operator password, checked once and exchanged for an
HMAC-signed session token that carries its own expiry. Stateless, so no session
table and no migration; self-expiring, so a dashboard left open on a lab machine
stops working rather than remaining a standing grant.

It fails closed. With `DASHBOARD_PASSWORD` or `TOKEN_SIGNING_SECRET` unset — or
the signing secret still at the template placeholder — every route under it
returns 503. A deployment that forgot the password gets a dashboard that does
not work, which is visible, rather than one quietly serving scan history to the
internet. The same reasoning as `require_auth` defaulting to true.

I built it in the backend rather than under `04_Extension/dashboard/` as the
WBS named. It is a server-rendered page plus four API routes, not code Gmail
loads. Change Log #41.

The metrics are labelled as operational counts, not model evaluation, and the
disagreement figure is labelled as user-reported. Precision and recall come
from the held-out set in `02_Model/evaluate.py`. A dashboard that put a
percentage next to the word "accuracy" would be the exact overstatement the
proposal commits to avoiding, and the label is in the interface rather than
only in the report.

**WBS 3.5, Google Safe Browsing.** Every other signal in the system is inferred
from the message itself, and the model behind them was trained on corpora from
2004–2007. This is the only input that knows something about the world today:
that a particular URL is currently serving malware.

It enters as a rule-layer signal rather than a model feature. The bundle was
trained on 43 features, so a 44th would require retraining and would invalidate
the per-feature contributions the explanations are generated from (WBS 2.2).
The rule layer already exists for deterministic checks that fire regardless of
model probability, and a flagged destination is exactly that kind of fact. It
takes the first floor at `dangerous` — the existing three floor at
`suspicious` — because where a link leads is not an inference about wording and
a low model probability is not a reason to soften it.

That change exposed a smaller one. The floor advice was a fixed string ending
"treat links and attachments here as untrusted", written when every floor was
`suspicious`. Telling someone a confirmed malware link is merely untrusted
understates it, so the advice now follows the tier it produced.

Caching uses the `url_reputation` table from WBS 3.1, keyed on `sha256(url)`.
Hits never leave the server; misses are batched into one request. Unsafe
verdicts expire on the `cacheDuration` Google returns, safe verdicts on a
12-hour TTL of ours — the API reports only matches, so "no match" carries no
duration, and a clean URL can turn malicious later.

The distinction the design turns on is between a clean answer and no answer. An
empty response means Google checked and found nothing, and is cached. A timeout
or an HTTP error means the question was never answered, and caching that as
"safe" would silently disable the signal for twelve hours on exactly the URLs
that could not be checked. They are kept strictly apart.

Writing the degradation tests found a real weakness. `check_record` called its
two helpers unguarded, so the module's promise that it never raises depended on
both of those functions continuing to catch everything internally. A scan
should not rest on that, so the guarantee is now enforced in the function
callers actually call. A separate case: a failed cache *write* was discarding a
verdict already in hand, which would have suppressed a warning about a link
known to be malicious. Both fixed.

**The privacy cost, recorded rather than glossed.** The Lookup API receives
full URLs, so addresses a user received leave the server and go to Google. Only
hashes are stored on our side, so the earlier claim — a database compromise
yields measurements, not mail — still holds exactly as written. But the
outbound call is a real disclosure. The Update API avoids it by matching hashed
prefixes against a locally maintained database, and that is materially more
work than this project has room for: a limitation, not a preference. Written up
in `00_Admin/data-handling.md` as Change Log #42. The extension's first-run
text says the message is sent for scoring and not stored; it does not yet
mention Safe Browsing, and would need amending before any deployment with real
users.

**WBS 4.6, the panel hang.** Found on 11/10 while testing against the deployed
stack. When the extension is reloaded or updated, the content script keeps
running in the page Gmail already rendered, but its connection to the extension
is severed and `chrome.runtime.sendMessage` throws *synchronously* — so the
callback never runs and the panel sits on its loading state indefinitely. That
is worse than an error: a spinner reads as "still checking" on a message that
was never checked.

Every call to the worker now goes through one guarded helper that normalises
the three distinct failures — dead context, dropped port, error response — so
no caller can forget one and leave the panel hanging. The terminal state also
disconnects the MutationObserver, which had been firing against a dead API on
every Gmail mutation for as long as the tab stayed open.

It cannot be found by reading the code, so there is a small harness
(`04_Extension/tests/context_invalidated_check.js`) that loads the content
script against a stubbed page and drives both invalidation paths plus the
healthy one.

## What did not get done

Safe Browsing is written but not active in production: the server needs
`SAFE_BROWSING_API_KEY`. The code treats a missing key as the signal being off,
so nothing is broken in the meantime — the verdict falls back to the model and
the existing rules.

## Notes

Set up the replacement laptop this week. The droplet is key-only with root
login and password authentication both disabled, so there was no password
fallback: the new key had to be authorized from the old machine before the new
one could connect at all. Worth remembering if the old laptop goes away before
another machine is enrolled.

The corpora and trained bundles are not in the repository by design, so they
exist only on the old laptop and the server. They need copying somewhere
durable before that machine is retired — WBS 1.6, 2.4 and 5.5 all read them,
and retraining against a different sample would make the IM1 numbers
incomparable with the final ones.
