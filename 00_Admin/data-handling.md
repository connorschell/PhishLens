# What PhishLens sends, computes and stores

**WBS 3.1 decision note.** Connor Schell · CYBR 498W · PhishLens · 2026-10-28

The schema is where this stops being a question of intent and becomes a
question of columns, so the decision is recorded alongside it.

## The choice

The extension can send the server either the message, or only the 43 numbers
measured from it.

**Sending only the numbers** is the stronger privacy position: no message
content leaves the browser at all. It requires reimplementing the parser and
all 43 measurements in JavaScript and keeping that implementation in exact step
with the Python used for training. Any drift between the two produces a model
scoring inputs that are subtly not the inputs it was trained on — which is the
same class of defect the WBS 1.4 review caught, and the hardest kind to notice,
because nothing fails loudly.

**Sending the message** keeps one parser and one feature extractor, shared
between training and production, which is the arrangement WBS 1.3 was built to
guarantee. The cost is that message content crosses the network.

## What was chosen, and the bound placed on it

The message is sent, and **no message content is stored**.

Subject, body and sender exist only in memory for the duration of the request.
What the database keeps is the 43 measurements, the score, the severity tier and
the explanation text. A `message_fingerprint` — a salted SHA-256 over the
normalized subject and body — lets a re-scan of the same message be recognised
without the message being recoverable from the row.

This is enforced by the schema rather than by discipline: the `scans` table has
no column that can hold a subject, a body or a sender address, so storing one
would require a migration, and a migration is a visible act.

## What this does and does not claim

- It does **not** claim the server never sees message content. It does.
- It does **not** remove the need for transport security. Production terminates
  TLS at Nginx (WBS 5.2) and the extension refuses plaintext origins.
- It **does** mean a compromise of the database yields measurements and scores,
  not anyone's mail.
- It **does** mean the retention question has a short answer: there is nothing
  to retain that would identify a message.

## Revisiting

Client-side feature extraction stays the better end state and is the natural
follow-on work after the system is end to end. The blocker is the dual
implementation, not the design. If the project finishes ahead of schedule in the
reserve period, this is the first thing to spend it on.

## Third-party disclosure: Google Safe Browsing (WBS 3.5)

Added 2026-11-17. This is the one place where data about a user's mail leaves
PhishLens entirely, and it is recorded here rather than left for a reader to
work out.

**What leaves.** The Lookup API is sent the **full URLs** found in the message,
up to ten per scan. Not hashes — full URLs, including any path or query string
the sender put in them. A tracking link of the form
`https://example.com/click?u=alice@university.edu` would carry that address to
Google along with it.

**What is stored here.** Only `sha256(url)`, in `url_reputation`, with the
verdict and an expiry (`schema.sql`). The URL itself is never written down on
this side, so the earlier claim — a database compromise yields measurements,
not mail — still holds exactly as stated.

**Why the weaker option was taken.** The Update API avoids the disclosure: the
client keeps a local database of hashed prefixes and only queries when a prefix
matches, so Google never learns which URL was actually checked. It also means
maintaining and refreshing that database, implementing the prefix-match logic,
and handling partial-hash collisions — well beyond what this project has room
for. The Lookup API is one POST. That is the whole reason, and it is a
limitation rather than a design preference.

**What reduces the exposure.** The cache: a URL already checked and unexpired
is answered locally and is not sent again. A deployment that leaves
`SAFE_BROWSING_API_KEY` blank makes no external call at all and loses only this
one signal.

**Consequence for the user-facing claim.** The first-run text below says the
message is sent for scoring and not stored. It does not currently say that
links may be sent to Google. If Safe Browsing is enabled in a deployment real
people use, that sentence needs amending — a privacy claim that is true of the
database but silent about an outbound third-party call is not honest enough.

## Where this is stated to the user

The extension's first-run screen (WBS 4.1) says in one sentence that the open
message is sent for scoring and is not stored. A privacy claim the user cannot
read is not a privacy feature.
