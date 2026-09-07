# Distribution

Written 7 September 2026. Two things here: what is genuinely ready, and an
honest read on the 1,000-users-in-a-week goal.

---

## 1. The thing you must not do

**Do not post this to patient communities.** Not r/cancer, not r/lungcancer,
not lung cancer Facebook groups, not patient advocacy mailing lists.

Those are the highest-traffic, most emotionally engaged audiences you could
reach, and posting there would probably be the fastest route to a thousand
visitors. It would also be the most harmful thing you could do with this
software:

- The tool says "not for patients" because eligibility is a clinical judgement
  it cannot make. Forty percent of criteria never compile, so "Eligible now"
  means "eligible on the criteria that compiled" — a distinction a frightened
  patient will not make.
- The corpus is a snapshot. Telling someone with metastatic lung cancer that a
  trial is open when the site closed enrolment a month ago is a real cost to a
  real person with limited time.
- A patient cannot act on the output anyway. Enrolment goes through their
  oncologist.

Every channel below is a professional or technical one. Keep it that way.

---

## 2. What "1,000 users" actually means here

Be precise about the number or you will optimise for the wrong thing.

| Metric | One week | Realistic? |
|---|---|---|
| Unique visitors | 1,000+ | **Yes**, if a technical post lands |
| People who run a match | 300–600 of those | Likely |
| Trial coordinators or clinicians | **10–40** | This is the honest ceiling |
| Coordinators who use it twice | 0–5 | Would be a genuine success |

There are only so many NSCLC trial coordinators in the world, they are busy,
and they do not browse Hacker News. A thousand *visitors* is very achievable in
a week. A thousand *users of the tool as intended* is not, and chasing it is
what would push you toward the patient communities you should avoid.

**Suggested goal instead:** 1,000 visitors, and 10 conversations with people who
actually screen patients for trials. The second number is the one that tells you
whether to keep building.

---

## 3. Channels, in the order I would use them

### Day 1 — Show HN
Your strongest asset is that the *engineering* is interesting to engineers:
compiling prose to executable predicates, 0 model calls, a measured comparison,
and an eval that found eight bugs. That is a Hacker News story even for readers
with no interest in oncology.

- Post Tuesday–Thursday, 8–10am ET.
- Title: `Show HN: I compiled 13,202 clinical trial eligibility criteria into executable predicates`
- Lead with the measurement, not the mission. Link `/about.html` — the honest
  limits page is the thing that earns trust with that crowd.
- **Be present in the comments for the first three hours.** That matters more
  than the post.

Realistic outcome: 300–3,000 visitors if it catches, ~0 if it doesn't. Front
page is a coin flip; a good post that misses is not a failed strategy.

### Day 1–2 — technical subreddits
r/programming, r/Python, r/compsci. Same framing. Read each subreddit's
self-promotion rule first; several ban it outright.

### Day 2–3 — the people who might actually use it
Slower, smaller, and worth more than all of the above:

- **AMIA** (American Medical Informatics Association) working groups, especially
  Clinical Research Informatics.
- **ACRP** and **SOCRA** — the professional bodies for clinical research
  coordinators. Both have forums and local chapters.
- **r/clinicalresearch** — actual coordinators, and they are blunt about tools
  that waste their time.
- LinkedIn: clinical research and health informatics. Post the honest version,
  including the TREC number you lose on.
- Your own oncology contacts. Ten warm introductions beat a thousand cold
  visitors.

### Day 3+ — durable, not spiky
- A short write-up of the eight bugs the eval found. That is a genuinely good
  engineering post and it will outlive the launch.
- The repository itself, with the README as the front door.

---

## 4. What to say

Frame consistently, in this order:

1. **What it is** — eligibility criteria compiled to executable predicates.
2. **What is measured** — 60.3% compile, 0 errors on 32 held-out numeric
   criteria, 0 model calls per query, deterministic across 20 runs.
3. **Where it loses** — TREC NDCG 0.36 against TrialGPT's 0.73, 40% of criteria
   never compile, lung cancer only, snapshot corpus.

Leading with (3) rather than hiding it is what makes (2) believable. Every
audience above has seen overclaiming health-AI demos and is primed to discount
them.

**Never claim** it is validated for clinical use, cleared by any regulator,
HIPAA-compliant, or a replacement for coordinator review. None of those are
true.

---

## 5. Measuring without breaking the privacy promise

The privacy page says no analytics and no trackers, and that is currently true.
Do not quietly add Google Analytics — the claim is the most credible thing on
the site.

Options that keep it true:

- **Vercel's request counts** (Project → Observability). Aggregate, no
  per-visitor identity, nothing added to the page. This is enough to count
  visitors and matches.
- **Vercel Web Analytics** is privacy-preserving and cookieless, but it *is*
  analytics and it adds a script. If you enable it, update `/privacy.html` the
  same day. Do not let the page say one thing while the site does another.

---

## 6. Before you post

- [ ] Read `/privacy.html` and `/terms.html` end to end and confirm you are
      comfortable standing behind every sentence.
- [ ] Decide whether Vercel's Hobby plan fits. It is for **non-commercial** use;
      a free research tool is fine, but read the terms yourself.
- [ ] Turn on **Vercel Firewall / Attack Challenge Mode** if traffic spikes. The
      in-code rate limiter does not work in production — measured: a 70-request
      burst returned 70 × 200, because Vercel spreads bursts across instances.
- [ ] Have an email you are willing to publish. `/privacy.html` and
      `/terms.html` currently point at `gelle.learning@gmail.com`.
- [ ] Re-run `python3 deck/figures.py` if you show the deck — its dates are
      derived from today.
- [ ] Decide what you will do if a patient emails you asking whether they are
      eligible for something. Write that reply *before* you launch.

---

## 7. Capacity

1,000 visitors is not a load problem. Rough numbers on Vercel Hobby
(100 GB bandwidth, 100 GB-hours compute per month):

- Page load ≈ 60 KB → 1,000 visitors ≈ 60 MB.
- A match is ~270 ms at 1 GB → 5,000 matches ≈ 0.4 GB-hours.

You have roughly two orders of magnitude of headroom. The cold start (~1 s on
first hit) is the only thing a visitor will notice.
