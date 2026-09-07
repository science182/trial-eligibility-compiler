# Show HN post

Every figure below was re-verified against the running system on 7 Sep 2026.
If you change code before posting, re-run `eval/compile_rate.py` and
`eval/differentiation.py` — HN will check these.

---

## Title

```
Show HN: Compiling clinical trial eligibility criteria into executable predicates
```

Alternatives, in order of preference:

```
Show HN: I compiled 13,202 trial eligibility criteria into executable predicates
Show HN: Trial eligibility matching with zero LLM calls at query time
```

Avoid "AI-powered", "revolutionise", and anything with an em-dash-and-adjective
cadence. That crowd discounts health-AI claims by default; plainness is the
whole strategy.

## URL

```
https://trial-eligibility-compiler.vercel.app
```

---

## Post body

> Clinical trial eligibility criteria are prose: "ANC ≥ 1.5 × 10⁹/L", "no
> chemotherapy within 4 weeks of first dose", "ALT ≤ 2.5 × ULN". Matching a
> patient means reading them by hand, one trial at a time.
>
> The current approach is to hand each criterion to an LLM and ask for a
> verdict, which puts the model in charge of the unit conversions, the
> threshold comparisons and the calendar arithmetic.
>
> This does it the other way round. Criteria are compiled once, offline, into
> typed executable predicates — nine types, covering labs, washouts, prior
> therapy, biomarkers, stage, histology, performance status, age and
> comorbidities. At query time it is ordinary Python: no model runs.
>
> Three things fall out of that:
>
> - It answers with a date. A trial blocked only by a washout is not
>   "ineligible" — it opens on a specific day, computed from the last-dose date
>   in the note. Real calendar arithmetic, so six months from 31 Aug is 28 Feb
>   and a leap year moves it.
> - Every verdict cites its source. Click a criterion and the exact sentence it
>   was computed from highlights in the note. It is a character offset, not a
>   similarity score.
> - It abstains. A field that was never recorded is unknown, not negative — and
>   it tells you which test would resolve it.
>
> What I measured, on 500 recruiting NSCLC trials from ClinicalTrials.gov:
>
> - 60.3% of 13,202 criteria compile to an executable predicate. The other
>   39.7% stay free text and are not evaluated at all.
> - 0 errors on 32 held-out numeric criteria, written after the system was
>   frozen and run once.
> - 0 model calls per query, ~65 ms for all 500 trials.
> - Deterministic: 20 identical runs, one SHA-256 over the whole output.
>
> Where it loses: on the TREC 2022 benchmark it ranks at NDCG@10 0.36 against
> TrialGPT's published 0.73. Those patient notes are ~600 characters with no lab
> values and no dates, so not a single washout or lab predicate can fire. That
> explains the gap; it doesn't erase it.
>
> The most useful thing I built was the evaluation, not the compiler. It found
> eight real bugs before it drew a single chart, and none had been caught by the
> 368 unit tests I had at the time. The worst: every exclusion criterion of six
> types was evaluating backwards, so a patient with a normal QTc was being
> blocked by a criterion excluding abnormal QTc. That was live in the UI.
>
> It's lung cancer only, the corpus is a fixed snapshot, and it is not for
> patients — eligibility is a clinical judgement this can't make. There's an
> honest limits page at /about.html.

---

## Your first comment (post immediately after)

Standard Show HN practice, and it is where the engineering detail goes.

> Author here. A few implementation notes for anyone interested in the messy
> parts:
>
> **Why compile rather than prompt.** The failure I cared about is silent. An
> LLM asked "is ALT 28 U/L within 2.5 × ULN?" will answer confidently whether or
> not it resolved ULN correctly, and you cannot tell from the output which
> happened. A compiled predicate either resolves the reference limit or refuses
> to compile.
>
> **Units are normalised at compile time, never at evaluation time.** 37% of lab
> criteria are expressed relative to a lab's own reference range (× ULN, × LLN)
> rather than absolutely, so the threshold isn't a number until you know the
> institution's limits.
>
> **Things that broke in ways I didn't expect:**
> - `eGFR` matched the *EGFR gene*, which appears in nearly every NSCLC trial.
>   Dropped the ambiguous abbreviation entirely.
> - HER2 expands to "human epidermal growth factor receptor 2", which contains
>   EGFR's long form verbatim — so every HER2 criterion compiled a phantom EGFR
>   predicate. Fixed with a lookbehind.
> - `≤ 1.5 × the upper limit of normal` parsed as an absolute 1.5 mg/dL because
>   of the word "the". A silent 50% error.
> - Bilirubin stole AST's ULN across a sentence boundary — a 33× threshold error.
>
> **The demo fixture rebases to today.** The persona was pinned to a fixed index
> date, so after that date passed the site kept announcing a trial "opens in 11
> days" for a day that had already gone. Every date in the note now shifts by the
> same delta, which preserves every interval and every verdict exactly. Then I
> found the server was returning UTC's tomorrow to anyone west of Greenwich, so
> the browser now sends its own local date.
>
> **Privacy.** No accounts, no cookies, no analytics, no third-party requests
> (CSP `default-src 'self'`). Files you pick are read in the browser and never
> uploaded. The text you match is sent to the server, held for one request, and
> discarded. I verified that by submitting a note with a canary string and
> grepping the platform's retained logs for it — it isn't there. Request
> metadata and IP are retained by the host, which the privacy page says plainly
> rather than claiming "we store nothing".
>
> **What I'd most like feedback on:** whether the four output states
> (eligible now / eligible from a date / needs data / not eligible) are the right
> decomposition, and whether the 39.7% that stays free text is the ceiling or
> just where I stopped.
>
> Happy to go into the compiler internals if anyone wants.

---

## Rules of engagement

- **Post Tue–Thu, 08:00–10:00 ET.** Do not post Friday or the weekend.
- **Be at your keyboard for the next three hours.** Response speed in the first
  hour matters more than the post text.
- **Do not ask anyone to upvote.** HN detects voting rings and it will kill the
  post and possibly the account.
- **Answer the sceptics first**, especially anyone saying "this should be an
  LLM" or "60% is low". Both are fair and you have real answers.
- **Never claim** clinical validation, regulatory clearance, or HIPAA
  compliance. If someone asks whether it's cleared: "No. It's a research tool,
  it's not a medical device, and it isn't for patients."
- **If a patient turns up in the thread** asking whether they're eligible for
  something: answer kindly, say the tool can't do that, and point them to their
  oncologist and ClinicalTrials.gov. Don't engage further in public.

## Likely hard questions

**"Why not just use an LLM? GPT-5 would nail these."**
Maybe on many of them. The point isn't that a model can't do it — it's that you
can't tell which ones it got wrong. Every verdict here is traceable to a line of
Python and a character offset. And I don't have the head-to-head number yet: the
prompted arm is built and fairness-audited but unrun, which I'd rather say than
imply a result I don't have.

**"60% compile rate isn't very good."**
It's the first published number for this that I'm aware of, and the hand-read
ceiling across all nine types is 70.4%, so the compiler reaches 86% of what the
schema can cover. The remaining 40% is genuinely unstructured — investigator
judgement clauses like "any condition that would contraindicate participation".

**"You lose badly on TREC."**
Yes, and it's on the same slide as the wins. The benchmark's notes contain none
of the inputs this runs on.

**"Is this useful with only 500 trials / one cancer type?"**
Not yet. It's a demonstration that the approach measures well on a narrow
domain. Breadth is the obvious next thing and I haven't done it.
