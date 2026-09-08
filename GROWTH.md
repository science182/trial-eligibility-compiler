# Getting to 5,000 visitors

Written 8 September 2026. Companion to `DISTRIBUTION.md`, which covers what
*not* to do and why; that document's constraints are not restated here and they
have not relaxed. Read it first.

Two halves: the instrument that tells you whether any of this is working, and
the plan.

---

## 1. Be precise about the number

5,000 visitors, free, is achievable. It is also a **portfolio outcome, not a
single event.** The arithmetic matters because it determines the strategy.

There is exactly one free channel that can deliver 5,000 on its own — the
Hacker News front page — and it lands maybe one time in five for a good post
in a niche category. Everything else is in the hundreds. So a plan built on
"post to HN and hope" is a plan with a 20% success rate, and a plan built on
twelve channels is one where no single miss is fatal.

| Channel | If it lands | Odds | Effort | One shot? |
|---|---|---|---|---|
| Show HN, front page | 3,000–15,000 | ~1 in 5 | 3h + a day in comments | **Yes** |
| Show HN, no traction | 30–150 | ~1 in 2 | same | |
| A separate HN story (the bugs write-up) | 1,000–8,000 | ~1 in 6 | a day to write | No — different artefact |
| r/programming | 500–5,000 | ~1 in 5 | 30m | |
| r/Python | 300–2,000 | ~1 in 3 | 30m | |
| Lobsters | 200–1,000 | ~1 in 3 | 15m | needs an invite |
| Console.dev (submit a tool) | 500–3,000 | ~1 in 5 | 20m | |
| PyCoder's Weekly / Python Weekly | 300–1,500 | ~1 in 3 | 15m each | |
| TLDR / Hacker Newsletter | 1,000–5,000 | ~1 in 20 | 10m | mostly picks from HN |
| Product Hunt | 200–1,500 | ~1 in 2 | 2h | |
| Comments on existing HN/Reddit threads | 50–500 each | high | 10m each | No — repeatable |
| LinkedIn, clinical-research audience | 100–800 | ~1 in 2 | 30m | |
| r/clinicalresearch, AMIA, ACRP | 50–300 | high | 1h | **worth the most** |
| GitHub topics, awesome-lists, AlternativeTo | 20–200/mo, compounding | high | 2h once | |
| Search, long tail | 0 for two months, then 100s/mo | high | free with the write-ups | |

Run all of it and the realistic band is **2,000–8,000 over two weeks**, with the
spread almost entirely determined by whether one of the two HN attempts catches.
Plan for the middle, be ready for the top.

### The number that actually matters

5,000 visitors is a vanity metric and you should hold it loosely. The three
numbers on `/stats.html` are ordered by how much they mean:

- **Visits** — how loud the post was.
- **Matches** — how many people got far enough to see the thing work. This is
  the real audience size.
- **Conversations with people who screen patients for trials** — not on the
  dashboard, because it is counted by hand, in your inbox. Ten of these is
  worth more than the other 4,990 visitors combined.

If you hit 5,000 visits and zero of the third, the launch succeeded and the
project did not learn anything.

---

## 2. The instrument

The site now counts itself. Three integers, published at
**`/stats.html`**, readable by anyone at `/api/pulse`.

- **Visits** — the page was opened (once per browser tab).
- **Documents** — a note was loaded, test document or the visitor's own.
- **Matches** — a match actually ran.

Plus one count per referring site, so you can tell HN traffic from Reddit
traffic without a tracker.

The implementation is `deploy/api/_counters.py`, and its constraint was that
every sentence on `/privacy.html` had to stay true. What that bought:

- No cookie, no stored ID, no hashed IP, no fingerprint. Nothing recorded can
  tell whether two visits came from the same person.
- Nothing from the note. Not the text, not its length, not what it matched.
- Never a full referring URL — only a host, and only one already named in the
  source. Everything else is `other`.

Because it stores integers rather than rows, there is no per-visit record for
anyone to request, subpoena, or leak. That is a property of the storage, not a
policy on top of it, which is the only kind of privacy claim worth making to
this audience. `/privacy.html` was updated the same day the counters shipped;
keep that habit.

### Switching it on

Unconfigured, every counter is a silent no-op — that is the default in the
repository, so a cloner gets a working site with no signup. To turn it on:

1. Vercel dashboard → your project → **Storage** → **Upstash for Redis** →
   create a free database, connect it to the project.
2. It injects `KV_REST_API_URL` and `KV_REST_API_TOKEN`. (A store created
   directly at Upstash sets `UPSTASH_REDIS_REST_*`; the code accepts both.)
3. Redeploy, open `/stats.html`, confirm it shows numbers rather than
   "not switched on".

Free tier: 256 MB and 500,000 commands a month. This uses four commands per
visit and two per match — **5,000 visitors costs about 25,000 commands, or 5%
of the monthly allowance.** It stays free past 100,000 visitors.

### The three decisions it should drive

Do not just watch the numbers go up. Each one answers a question you will
actually face during the launch week:

| Reading | What it means | What to do |
|---|---|---|
| Matches / visits **below ~15%** | People arrive and leave without trying it | The landing page is not making the case in five seconds. Fix the page before spending the next channel. |
| Matches / visits **above ~35%** | The page is converting well | Spend every channel you have. The bottleneck is traffic, not the product. |
| Documents high, matches low | People load a note and stop | Something between loading and matching is confusing or slow. Watch it yourself on a cold instance. |
| One source dominating | You have one channel, not a portfolio | Post the second artefact somewhere else entirely. |

Screenshot `/stats.html` at the end of each day. Vercel's per-day counters
expire after 400 days and daily numbers are the only record you will have.

---

## 3. Week 0 — before any traffic

Six things, none of which can be done after the post goes up.

- [ ] **Switch on the counters** (above) and confirm `/stats.html` reads. Going
      viral without instrumentation is the one unrecoverable mistake here.
- [ ] **Warm the instance and time a cold start.** The first hit after idle is
      ~1s. On an HN spike most visitors get a warm one, but the first hundred
      do not. Know the number so you are not surprised by a comment about it.
- [ ] **Turn on Vercel's firewall** (Project → Firewall). The in-code rate
      limiter does not work in production — measured, 70 requests returned
      70 × 200, because Vercel spreads a burst across instances.
- [ ] **Write the reply to a patient before you need it.** Someone will email
      asking whether they are eligible for something. Have that answer written
      and kind, in a draft, before launch day.
- [ ] **Read `/privacy.html` and `/terms.html` end to end** and confirm you
      will stand behind every sentence under hostile questioning. You will get
      hostile questioning; it is the correct response to health AI, and the
      pages are built to survive it.
- [ ] **Decide the Hobby-plan question.** Vercel Hobby is for non-commercial
      use. A free research tool is fine; read the terms yourself and decide
      before traffic makes it urgent.

---

## 4. The sequence

Two weeks. The ordering is deliberate: the cheap high-signal channels go first
so the landing page is already fixed by the time the expensive one-shot fires.

### Days 1–2 — the quiet channels, and a real audience

Start where a miss costs nothing and the feedback is worth the most.

- **r/clinicalresearch.** Actual coordinators, blunt about tools that waste
  their time. 50–300 visitors and possibly your first real conversation.
- **AMIA Clinical Research Informatics working group**, **ACRP**, **SOCRA**.
  Slow, small, correct audience.
- **Ten warm introductions** from your own oncology contacts. This is the
  highest-value hour in the whole plan and it is not a growth channel; it is
  the reason the growth channels exist.
- **LinkedIn**, clinical research and health informatics. Post the honest
  version including the TREC number you lose on.

Then read `/stats.html`. If match rate is under 15%, **stop and fix the landing
page.** You will not get the Show HN attempt back.

### Day 3 — Show HN

The one-shot. `SHOW_HN.md` has the post; the mechanics:

- Tuesday–Thursday, 8–10am ET.
- **Be in the comments for the first three hours.** This matters more than the
  post text. A thin post with a present author beats a polished one with an
  absent author, every time.
- Answer the "isn't this just an LLM wrapper" question with the 0-model-calls
  header and the determinism measurement. That question is coming.
- **Do not ask anyone to upvote.** It is against the rules, it is detectable,
  and it will get the post killed.

If it front-pages, do nothing else that day except answer comments. If it
doesn't, that is the modal outcome and the plan continues.

### Days 4–5 — the aggregators

Only after HN, because several of them pick up from HN and a same-day
cross-post looks like spam.

- **Lobsters** (needs an invite — ask someone before launch week, not during).
- **r/programming** and **r/Python.** Read each self-promotion rule first;
  several ban it outright and a ban costs you the account.
- **Console.dev** tool submission, **PyCoder's Weekly**, **Python Weekly**,
  **Hacker Newsletter**. All free, all take ten minutes, all curated — so the
  submission should read like the newsletter's own blurb, not like a pitch.

### Days 6–9 — write the second artefact

This is the part most launches skip and it is the difference between 2,000 and
5,000. You have one genuinely good engineering story that is **not** the tool:

> **The eval found eight real bugs before it drew a single chart, and 368 unit
> tests had missed all of them. Every exclusion criterion of six types was
> evaluating backwards — a patient with a normal QTc was being blocked.**

That is a post about testing, not about oncology, and it has a much wider
audience than the tool does. It is also a legitimate second HN submission,
because it is a different artefact — not a resubmission.

A second candidate: **60.3% of eligibility criteria compile to an executable
predicate.** Nobody has published that number. It is a small research result
and it will be cited more than the tool will be used.

Both link back. Both keep working for months. Both are free.

### Days 10–14 — the compounding tail

- GitHub **topics** on the repo (`clinical-trials`, `nlp`, `healthcare`,
  `python`), and pull requests to the relevant **awesome-** lists.
- **AlternativeTo**, **Product Hunt**, open-source tool directories.
- **Comment, don't post.** When an HN or Reddit thread comes up about clinical
  trials, matching, or LLM determinism, leave a genuinely useful comment that
  happens to link the tool. This is repeatable, it never gets old, and over a
  month it reliably out-performs any single post.

---

## 5. If it works, and if it doesn't

**If a post catches:** answer every comment, watch `/stats.html` hourly, and
resist shipping features people ask for in the thread. Launch-day feature
requests come from people who will never use the tool. The requests that matter
come from the coordinator who emails you on day nine.

**If both HN attempts miss:** that is a 60% likely outcome and it is not a
failed strategy. The tail channels still reach 1,500–2,500 over a month, and
the write-ups keep earning search traffic. The honest move at that point is to
stop optimising distribution and go back to the one measurement that is
missing — see below.

---

## 6. What is still missing, and it is not traffic

The prompted-baseline arm of the evaluation has never been run. It needs a free
`GEMINI_API_KEY` and an afternoon.

Until it runs, "better than an LLM at numeric criteria" is an argument. After it
runs, it is a result — and it is the single sentence most likely to make the
second HN post land. **It is worth more than any channel in section 1.**

---

## 7. Capacity and cost

5,000 visitors is not a load problem. On Vercel Hobby (100 GB bandwidth,
100 GB-hours compute per month):

| | 5,000 visitors | 50,000 visitors |
|---|---|---|
| Bandwidth (~60 KB/load) | 0.3 GB | 3 GB |
| Compute (~270 ms at 1 GB) | ~0.4 GB-hours | ~4 GB-hours |
| Counter commands | ~25,000 | ~250,000 |
| Cost | £0 | £0 |

Two orders of magnitude of headroom. The only thing a visitor notices is the
~1s cold start on the first hit after an idle period.

---

## 8. When to stop

Set these before you start, because they are much harder to judge in the middle
of a good day.

- **5,000 visits and fewer than 3 conversations with people who screen
  patients** → the audience is engineers, not coordinators. Interesting
  project, wrong distribution thesis. Say so and decide deliberately whether
  you are building a tool or a paper.
- **Any pressure to post in a patient community** → the answer is no, and it
  stays no at 500 visitors. See `DISTRIBUTION.md` §1.
- **Any pressure to soften `/about.html`** → the limitations page is the reason
  the numbers on it are believed. Losing it would cost more than it earns.
