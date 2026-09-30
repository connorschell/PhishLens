# Git Remote Access

How PhishLens gets pushed to GitHub, and where the credential lives.
Connor Schell · 2026-09-30

Repository: <https://github.com/connorschell/PhishLens> (private)

---

## The split

**Committing needs no credential.** Commits are local. Claude commits every
working session whether or not a token exists, so the history is always being
built.

**Only pushing needs a credential.** Two ways to do it:

| | Who pushes | Credential |
|---|---|---|
| A | Connor, from Windows | GitHub Desktop, authenticated once via browser |
| B | Claude, from the session | Token in `.git_token`, read at push time |

Both can be true at once. A is the safer default; B exists so a session can
finish the job without waiting on you.

## Option B setup

1. Create a **fine-grained** personal access token:
   Settings → Developer settings → Personal access tokens → Fine-grained.
   - Repository access: **Only select repositories** → `PhishLens`
   - Permissions: **Contents → Read and write**. Nothing else.
   - Expiration: **90 days** is reasonable for a semester project. Put the
     expiry date in your calendar — an expired token fails the push with a
     confusing 403, and you will not remember why.
2. Save it to `.git_token` in the capstone folder root. One line, no quotes.
3. That path is in `.gitignore`. Verify before the next push:
   `git check-ignore -v .git_token` should print a match.

Then `./push.sh` pushes, and Claude uses the same path.

## Why a file and not a chat message

A token pasted into a conversation is stored in that conversation. A token in a
file is read at the moment it is needed and never printed. Claude does not
retain credentials between sessions, so a pasted token would have to be pasted
again every time — each paste another copy.

## What the token can and cannot do

Scoped as above, it can read and write **this one repository**. It cannot touch
other repos, account settings, billing, or org resources. If it leaks, the blast
radius is the contents of PhishLens — bad, since this is graded coursework
someone could tamper with or copy, but bounded and fixable by revoking it.

## Known weakness: OneDrive

The capstone folder is inside OneDrive, so `.git_token` syncs to CNU's tenant.
That is not a disaster for a repo-scoped token, but it is not ideal either.

The better arrangement is to move the working copy somewhere unsynced —
`C:\dev\PhishLens` — and connect that folder to the Claude session instead. That
fixes this and the git lock-file problems OneDrive already caused on 2026-09-30
in one move. Worth doing before the project gets larger.

## Rotation

Revoke and reissue if: the token appears in a chat, an email, or a screenshot;
the laptop is lost; or the semester ends. Revoking is instant and breaks nothing
except pushing — commits and history are unaffected.

## Current token

**Expires 2026-10-30 16:32 UTC.** Confirmed from the API response header, not
assumed. That is 30 days, which covers through Weekly Update #5 — it will expire
**before** the project ends on 2026-12-07, so it has to be rotated once mid-term.

Put "rotate PhishLens GitHub token" in your calendar for the week of 2026-10-26.
An expired token fails the push with a 403 that does not say "expired", and you
will lose twenty minutes to it otherwise.

This token was pasted into a chat transcript during setup on 2026-09-30 and kept
rather than reissued — a deliberate call, on the grounds that its blast radius is
one private coursework repo. That reasoning stops holding if the repo ever
carries anything real: a live API key, the Safe Browsing key, VPS credentials,
or `.env` with production values. None of those belong in git regardless, which
is what `.gitignore` is enforcing.

## Rotation log

| Date | Action | Reason |
|---|---|---|
| 2026-09-30 | Token #1 issued, scoped to PhishLens, Contents read/write, expires 2026-10-30 | Initial push of WU2 work |
| _due week of 2026-10-26_ | Rotate token #1 | Expiry |
