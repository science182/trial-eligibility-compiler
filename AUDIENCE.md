# Who would actually use this

Written 8 September 2026. `GROWTH.md` is about getting 5,000 visitors.
This is about the far smaller number hiding inside them.

Everything in section 1 comes from the corpus you already have — regenerate it
with `python3 outreach/audience.py`.

---

## 1. What the data says

500 recruiting NSCLC trials. Counting the sites running them:

- **4,989 distinct organisations** are running at least one of these trials.
- **2,873 of them run exactly one.**
- The top 20 organisations account for **5%** of site-trial pairs.

That last number is the whole strategy, and it is the opposite of what a target
list usually looks like. This is not a market you win with twenty enterprise
conversations. There is no small set of institutions that, once convinced,
brings the rest.

The head of the distribution is still worth having:

| Trials | Organisation | Main site |
|---:|---|---|
| 51 | MD Anderson Cancer Center | Houston, TX |
| 46 | Memorial Sloan Kettering | New York, NY |
| 42 | Sarah Cannon Research Institute | Nashville, TN |
| 31 | Dana-Farber Cancer Institute | Boston, MA |
| 31 | Washington University / Siteman | St Louis, MO |
| 26 | City of Hope | Duarte, CA |
| 25 | Mayo Clinic · Mass General Brigham · NEXT Oncology · Northwestern · UC San Diego | |
| 24 | NYU Langone · Samsung Medical Center | |
| 23 | Ohio State James · Hospital 12 de Octubre (Madrid) | |
| 22 | Cleveland Clinic · Moffitt · Yale | |

Full ranking: `outreach/organisations.csv` (4,989 rows).

### Two constraints the data makes concrete

**Language.** China has the most trials of any country (230 of 500 have a site
there), and the tool is English-only. Only **238 of 500 trials** have a site in
an English-speaking country, and **2,285 of 4,989 organisations**. Your
addressable audience is a little under half of what the ranking shows. Say the
scope out loud in outreach; a Shanghai Chest Hospital coordinator finding out
after signing in is a worse outcome than never reaching them.

**Metro concentration.** Houston (81 trials), New York (69), Fairfax VA (57),
Nashville (56), Los Angeles (53), Boston (50). If you ever do anything in
person — a site visit, a local ACRP chapter talk — those are the six places
where it is worth the trip.

---

## 2. The reframe that matters more than the list

Look at what the tool actually does: **one patient → 500 trials.**

That is not the shape of a site coordinator's job. A coordinator at MD Anderson
has the opposite problem — **one trial → many patients**. They are screening
their own portfolio, they already know their 51 trials, and they need to find
patients for them. This tool answers a question they did not ask.

The person whose real question this *is*:

1. **The community or referring oncologist.** Sees a stage IV NSCLC patient at
   a practice with no trial portfolio of its own. The question is literally "is
   there a trial anywhere for this person?" — one patient against everything.
   This is the best fit in the product as it stands, and it is not the audience
   `DISTRIBUTION.md` originally aimed at.
2. **Patient navigators and trial-matching services.** Their whole job is
   one-patient-to-many-trials. Massive Bio appears in your own corpus. Others:
   TrialJectory, Leal Health, the LUNGevity and GO2 Foundation navigators.
   These are organisations, not individuals, and they will evaluate a tool
   properly rather than glancing at it.
3. **Clinical research informatics people.** Not users — evaluators. They will
   care about the 60.3% compile rate and the determinism result more than about
   the interface, and they are the ones who cite things.
4. **Site coordinators at large centres** — a real but *secondary* audience, and
   only for the pre-screen: run a new patient once, see which of our trials they
   are not blocked from. Useful, narrower than the pitch suggests.

Order your outreach by that list, not by trial count. The 51-trial centre is the
most impressive name and roughly the fourth-best fit.

---

## 3. Where these people actually are

Named, in the order I would spend time on them.

**Highest value, lowest volume — do these first**

- **Your own oncology contacts.** Ten warm introductions. Still the single best
  hour available, and it is not a growth channel; it is the reason the growth
  channels exist.
- **Patient navigation organisations** — LUNGevity, GO2 for Lung Cancer, the
  navigator teams at large systems. Email the organisation, not a trial contact.
- **r/clinicalresearch.** Real coordinators, blunt, and they will tell you fast
  if the shape is wrong.

**Professional bodies — slow, correct**

- **ACRP** (Association of Clinical Research Professionals) and **SOCRA** —
  forums, local chapters, and both run conferences with poster tracks.
- **AMIA**, Clinical Research Informatics working group. This is where audience
  (3) lives, and where a 60.3% compile-rate result gets read properly.
- **ASCO**'s and **IASLC**'s online communities for lung specifically.
- **SCOPE** and **DPHARM** for the trial-operations crowd.

**Where the wrong-but-loud audience is**

Hacker News, r/programming, Lobsters. These reach engineers. That is fine and
`GROWTH.md` still recommends them — engineers are how a project gets known and
occasionally how a coordinator hears about it second-hand — but do not confuse
a good HN day with finding a user.

---

## 4. The contact data question

ClinicalTrials.gov publishes a named contact person, with an email and often a
phone number, for most recruiting trials. It is right there in the API.

**Do not mail that list.** That address is published so patients and referring
physicians can ask about *that specific trial*. Using it to market a tool is a
misuse of it, however good the tool is — and in this field, being the person who
spammed 500 research nurses is a reputation you do not recover from. It may also
put you the wrong side of CAN-SPAM and GDPR, but the reason to not do it is not
the statute.

`outreach/audience.py` therefore reads facilities only and never touches a
contact field. That is deliberate, and it should stay that way.

**The line I would draw:** ten to twenty genuinely personal emails to people you
have a real reason to write to — you read their trial, the tool has something
specific to say about it, you say who you are and what you want — is normal
professional correspondence. Five hundred templated ones is spam. The difference
is not the number; it is whether you could have written the email without the
list.

---

## 5. What to say

Lead with the fit, not the technology:

> A patient walks in with stage IV lung adenocarcinoma. This checks them against
> 500 currently-recruiting trials in about a tenth of a second, tells you which
> ones they are blocked from and why, and — for the ones with a washout period —
> the date they become eligible rather than just "no".

Then the credibility, in this order, because leading with the loss is what makes
the wins believable:

- It ranks worse than TrialGPT on the public TREC benchmark: 0.36 against 0.73.
- 40% of criteria never compile and it abstains on those rather than guessing.
- Lung cancer only, English only, and a fixed registry snapshot.
- Which is why: 60.3% of criteria *do* compile, 0 errors on 32 held-out numeric
  criteria, 0 model calls per query, identical output across 20 runs.

**Never claim** clinical validation, regulatory clearance, HIPAA compliance, or
that it replaces coordinator review.

The single question worth asking at the end of every conversation: **"what did
it get wrong on a real note?"** You cannot answer that from the analytics and it
is the only thing that tells you what to build next.

---

## 6. Finding them inside the traffic

Anonymous traffic cannot tell 5,000 engineers from 5,000 coordinators, so the
tool now asks. Twelve seconds after a match renders, one quiet line appears:

> Who did this reach? · **I screen patients for trials** · Clinician ·
> Researcher · Engineer · Just curious

Optional, one tap, never before a match, gone once answered or dismissed. It
adds one to a total for that answer — a word from a fixed list, attached to
nobody. The breakdown is public on `/stats.html` alongside the other counters,
and `/privacy.html` describes it.

Answering **"I screen patients for trials"** reveals your email with a specific
ask: tell me what it got wrong on a real note. That reply is the conversion this
whole document is about. Everything else is traffic.

**The number to watch is not the percentage.** At 5,000 visitors, 1% is fifty
people who screen patients, and ten replies from them would be a genuinely
successful launch. If the answer comes back 95% engineer, that is not a failed
launch — it is the finding that this reached the wrong room, and it is much
better to learn it from a counter than from six months of building.
