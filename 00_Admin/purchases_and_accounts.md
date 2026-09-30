# Purchases and Accounts

**Task A-17.** Everything PhishLens needs an account, a domain, or money for,
and who has to do it.
Connor Schell · CYBR 498W · last updated 2026-09-30

Costs below were checked on 2026-09-29. Anything marked **verify** should be
confirmed on the provider's page before money is spent, because student-offer
terms change without notice.

---

## 1. Accounts to create

| # | Account | Why the project needs it | Cost | Status | Owner |
|---|---|---|---|---|---|
| 1 | **GitHub Student Developer Pack** | Unlocks the free domain and hosting credit below; also private repos and Copilot | Free with `.edu` verification | **Not created** | Connor |
| 2 | **GitHub account / repo** | Version control for the whole project; required for the final report's code submission | Free | **Not created** | Connor |
| 3 | **Domain registrar** | The API needs a hostname for a Let's Encrypt certificate (WBS 5.2). A bare IP cannot get a public TLS cert | See §2 | **Not created** | Connor |
| 4 | **VPS provider** | Production host for the API, database, and Nginx (WBS 5.1) | See §3 | **Not purchased** | Connor |
| 5 | **Google Cloud project + Safe Browsing API key** | URL reputation as one weighted input (WBS 3.5) | Free tier | **Not created** | Connor |
| 6 | **Chrome Web Store developer account** | Only if the extension is published rather than side-loaded — see §5 | One-time fee, **verify** | **Decision pending** | Connor |
| 7 | **Two throwaway Gmail accounts** | End-to-end testing against live Gmail with seeded messages (WBS 5.4) — never a personal or CNU account | Free | **Not created** | Connor |

**Do #1 before #3 and #4.** The Student Pack is what makes the domain and the
hosting credit free; registering them first means paying for them.

## 2. Domain

The Student Pack includes a free first-year domain from Namecheap (historically a
`.me`), and `.tech` and `.dev` offers have appeared and disappeared over the
years — **verify** which is current at the time of registration.

A `.me` or `.dev` name is sufficient. Requirements:

- Registrar must expose DNS records (an `A` record pointing at the VPS IP).
- Nothing else. No email, no privacy add-ons, no hosting bundle.

Budget if the free offer is unavailable: **$10–15/year**.

## 3. VPS

Purchased at WBS 5.1 (week of 11/4), not before — paying for an idle server for
five weeks is wasted money, and the provisioning steps are the task.

Sizing for this workload — FastAPI, PostgreSQL, a scikit-learn model held in
memory, single-digit concurrent users:

| Spec | Minimum | Comfortable |
|---|---|---|
| RAM | 2 GB | 4 GB |
| vCPU | 1 | 2 |
| Disk | 25 GB SSD | 50 GB SSD |
| OS | Ubuntu 22.04 or 24.04 LTS | same |

2 GB is enough to serve the model but tight for building Docker images on the
box; 4 GB avoids that. Expected cost **$6–12/month**, so **$12–24** for the
remainder of the semester.

The Student Pack's DigitalOcean credit (historically $200, **verify**) should
cover the entire project if it is still on offer. Otherwise any provider with
Ubuntu LTS and a public IPv4 address works — the deployment is plain Docker
Compose and Nginx, with nothing provider-specific.

## 4. Google Safe Browsing

The Lookup API is free for this volume. Steps:

1. Create a Google Cloud project.
2. Enable the Safe Browsing API.
3. Create an API key and restrict it to that API.
4. Put the key in the server's `.env` as `SAFE_BROWSING_API_KEY`. It never goes
   in the extension — see `auth-design-revision.md`.

Billing account attachment is **verify**: Google has required one on some APIs
even inside the free tier. If it does require a card, the free quota still covers
this project's volume; set a budget alert at $1 so a mistake is visible
immediately.

Design already accounts for absence: if the key is missing or the call fails,
Safe Browsing degrades to an unavailable input and the score is produced from
the remaining features, with the explanation panel saying so.

## 5. Chrome Web Store — decision needed

Publishing is **not required** by the proposal. The IM2 demo and the final demo
both work with the extension loaded unpacked via `chrome://extensions` in
Developer Mode, which costs nothing and avoids review delay.

Publishing costs a one-time developer registration fee (**verify** current
amount) and adds a review queue that could land after the demo date.

**Recommendation: do not publish.** Load unpacked for both demos, and note the
packaging steps in the installation documentation (WBS 5.5) so the work is
represented in the report without spending money or risking a review delay.

## 6. Test Gmail accounts

Two fresh Google accounts, created solely for WBS 5.4. Seeded with sample
messages drawn from the corpora so the end-to-end test exercises real phishing
structure without forwarding anything from a real inbox. Never use a personal or
CNU account — the content script reads message content from the page.

## 7. Total expected spend

| Item | Low | High |
|---|---|---|
| Domain | $0 (Student Pack) | $15 |
| VPS, Nov–Dec | $0 (Student Pack credit) | $24 |
| Safe Browsing | $0 | $0 |
| Chrome Web Store | $0 (not publishing) | one-time fee if published |
| **Total** | **$0** | **~$39 plus any store fee** |

## 8. Next actions for Connor

1. Verify the Student Developer Pack with the CNU email address.
2. Create the GitHub account and push the repository that was scaffolded today
   (WBS 1.2) — it is already a local git repo with one commit.
3. Claim the free domain and point nothing at it yet.
4. Create two test Gmail accounts.
5. Create the Google Cloud project and Safe Browsing key.
6. Leave the VPS until WBS 5.1 in the week of 11/4.
