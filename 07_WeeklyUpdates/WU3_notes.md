# Weekly Update 3 — Connor Schell — CYBR 498W — PhishLens

Week ending Tuesday, October 7, 2026

---

## What I finished in week 2 (recap)

- Downloaded the training emails and cleaned them into one consistent format. Ended up with 12,698 usable emails: 6,818 phishing, 4,091 normal, 1,789 junk mail.
- Removed 1,790 phishing emails that were duplicates of each other — the same scam sent over and over with a different tracking number in it.
- Set up the project folder, the code repository, and the container setup that the server will eventually run on.
- Rewrote the login design for the browser extension after the feedback on my proposal. A browser extension cannot hide a password inside itself, so instead each installation now asks the server for its own identifier when it is first installed.
- Put everything on a private code repository on GitHub so there is a dated record of the work.

Still open from week 2: fixing the page numbers in the table of contents of my proposal — I need to put that document in the project folder first.

---

## What I did this week

### Built the email reader

- Wrote one piece of code that reads an email and pulls out the pieces that matter: who sent it, what the subject is, what the message says, every link in it, and any attachments.
- Made it work two ways with the same code: reading emails from my training files, and reading an email straight off the screen in Gmail. This matters because the model has to see the exact same thing when it is being trained and when it is actually being used. If those two drifted apart, the model would work in testing and fail in the real world.
- Wrote 24 automated tests for it, built around the messy real cases I found in the training emails — 141 emails with no message body, 40 with a broken date, 48 with a broken character encoding.

### Built the feature extractor

- This is the part that turns an email into numbers the model can learn from. There are 43 of them.
- Examples: does a link display one website address but actually go to a different one; does the sender claim to be a well known company while sending from an unrelated address; does the message pressure you to act immediately; is the link using a web address ending that is cheap to register and commonly abused.
- Every single one of the 43 is written so it can be explained to a person in one sentence. That was a hard rule, because the whole point of this project is telling the user why something was flagged, not just that it was.

### Built the training and testing split

- Split the emails into a set for teaching the model and a separate set for testing it.
- Wrote the data dictionary that documents all 43 numbers, which is one of my required deliverables.

### Had the work independently reviewed

I ran a separate review pass over all of this code specifically looking for mistakes. It found several real ones, and I fixed all of them. The four that mattered most:

- **The model was about to learn the wrong thing entirely.** My three strongest signals were really just measuring the difference between email in 2002 and email in 2022. My phishing emails are recent and my normal emails are from 2002, so "this email is formatted as a web page" looked like a perfect phishing detector. It is not — it just means the email is modern. Worse, in real Gmail that signal would be true for basically every message, so the model would have flagged everything as phishing. I removed those signals.
- **One signal was using information Gmail will never give me.** It was reading a hidden delivery header that is not visible on the screen. It also turned out to be backwards — it was firing on 62 percent of normal email and only 19 percent of phishing. Removed.
- **A quarter of my test emails were really the same scam campaigns as my training emails.** Testing a model on emails it has effectively already seen produces a great score that means nothing. I rewrote the split so entire campaigns go to one side or the other. The overlap went from about 30 percent to zero.
- **Word matching was too loose and would have produced embarrassing explanations.** The word "chase" was being found inside "purchase", so a receipt would have been reported to the user as "this message claims to be from Chase". Fixed, with tests so it cannot come back.

---

## What I am doing next week

- Train the first model and build the evaluation around it. This is the biggest single task in the project, estimated at ten hours.
- Measure it on precision, recall, and false positive rate — not accuracy. Accuracy would be misleading here because phishing is 54 percent of my training data and nothing close to that in a real inbox.
- Run the measurement twice: once with all 43 signals, and once with the six questionable ones removed. If the score barely moves, those signals were honest. If it collapses, the model was reading the calendar rather than the email. Either way that comparison goes in the final report.
- Check what Gmail actually gives the extension to read. There is one open question I cannot answer from my training files: Gmail may rewrite every link in an email before it reaches the screen. If it does, several of my link signals break in the real product. I have written the code to handle it, but I need to confirm it against a real message.
- Fix the table of contents page numbers in my proposal.

---

## What changed from my original proposal

- **The email reader came in faster than planned** — two hours instead of six — because a lot of it was already written as part of last week's work.
- **The training and testing split got pushed back a few days** and was finished alongside this update rather than earlier in the week, because the review above found problems I chose to fix before moving on.
- **Four of the signals I planned were removed** after the review showed they were measuring the age of the email rather than whether it was phishing.
- **The backend framework decision was made early**, in week 2 rather than week 5, because the container setup needed a framework chosen before it could be written.

---

## The one thing worth showing

If you want to look at one thing: the data dictionary at `01_Data/feature_dictionary.md`. It lists all 43 signals, what each one measures, the sentence the user will be shown when it fires, and — honestly — which ones I do not fully trust yet and why.
