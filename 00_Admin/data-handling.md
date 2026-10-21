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

## Where this is stated to the user

The extension's first-run screen (WBS 4.1) says in one sentence that the open
message is sent for scoring and is not stored. A privacy claim the user cannot
read is not a privacy feature.
