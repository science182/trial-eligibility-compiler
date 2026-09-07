# Clinical Trial Eligibility Compiler

Compiles free-text clinical trial eligibility criteria into executable typed
predicates, evaluates them deterministically in Python, and reports specific
eligibility dates rather than categorical labels.

**Scope: non-small cell lung cancer, English, local web UI.**

## Status

| Stage | State |
|---|---|
| 1. Data acquisition + reality check | done |
| 2. Criterion compiler | **done** — all 9 predicate types |
| 3. Evaluation engine + patient extraction | **done** — evaluator, extractor, aggregation |
| 4. UI | **done** — three screens, zero dependencies |
| 5. Retrieval + benchmark | **done** — 9.2, 9.4, retrieval recall |

## Stage 1 results

- **500** recruiting interventional NSCLC trials (of 1,079 available), all with
  eligibility text, median 3,206 chars → **14,510 criteria**, 29.0 per trial.
- TrialGPT cached TREC files download and parse (**gate PASS**, 9.4 open).
  Source repo is `ncbi-nlp/TrialGPT`. TREC 2021/2022 ship `retrieved_trials.json`
  (the cached candidate pool), not `corpus.jsonl` — that exists only for SIGIR.
  TREC 2022: 50 patients, 12,682 candidate trials, 35,395 qrels rows.
- Hand-read type distribution over 30 blocks (695 criteria after the splitter
  rewrite): **70.8% of criteria carry at least one typed predicate** (47.8%
  excluding COMORBIDITY). Both clear the 40% kill threshold.

## Stage 2 results

Measured on the 500-trial corpus (13,202 criteria) and scored against the
hand-read gold set:

| type | criteria | predicates | % of criteria | precision | recall | F1 |
|---|---|---|---|---|---|---|
| COMORBIDITY | 3,461 | 5,515 | 26.2% | 0.868 | 0.886 | 0.877 |
| WASHOUT | 1,793 | 2,858 | 13.6% | 0.946 | 0.907 | 0.926 |
| LAB_THRESHOLD | 1,139 | 2,407 | 8.6% | 1.000 | 0.906 | 0.951 |
| PRIOR_THERAPY | 1,007 | 1,336 | 7.6% | 0.852 | 0.812 | 0.832 |
| STAGE | 750 | 750 | 5.7% | 0.933 | 0.800 | 0.862 |
| HISTOLOGY | 708 | 708 | 5.4% | 0.853 | 0.935 | 0.892 |
| BIOMARKER | 473 | 992 | 3.6% | 0.926 | 0.806 | 0.862 |
| PERFORMANCE_STATUS | 432 | 432 | 3.3% | 1.000 | 0.931 | 0.964 |
| AGE | 362 | 362 | 2.7% | 1.000 | 0.957 | 0.978 |
| **combined** | **7,964** | **15,360** | **60.3%** | | | |

**100% of trials (498/500) have at least one compiled criterion.** The hand-read
ceiling across all nine types is 70.4% of criteria, so the compiler reaches 86%
of what the schema can cover. Every type is at or above 0.85 precision.

### COMORBIDITY

The largest type, and the one where the "name it or don't compile it" rule does
the most work. Registry text is full of unnamed catch-alls — *"any other
concurrent severe and/or uncontrolled medical condition that would, in the
investigator's judgement, contraindicate participation"* — which state a real
restriction but nothing a patient record can be checked against. Those stay
FREE_TEXT. So do hypersensitivity, pregnancy, and concomitant medication, which
the hand labels also treat as non-comorbidity.

`qualifier` is tracked separately from `condition` because the verdict usually
turns on it: *active* brain metastases block, *treated and stable* brain
metastases do not, and the condition token is identical in both. Qualifier
lookup is clause-bounded so "active infection; stable brain metastases are
eligible" does not lend *active* to the metastases, and it includes the matched
span itself because several patterns absorb their own qualifier ("severe
hepatic disease", "unstable angina").

`excluded` is derived from section polarity plus any negation, so the predicate
reads the same way regardless of which section the trial filed it under:
permission language ("are eligible", "may enrol") sets it False; otherwise an
exclusion-section mention is True and an inclusion-section mention is True only
when negated. Where the splitter already flipped "must not have", that negation
is not read again.

One trap worth naming: inline abbreviations. "central nervous system (CNS)
metastases" is the registry's house style and splits every phrase pattern.
Parentheticals matching `([A-Z][A-Z0-9/-]{1,9})` are blanked with spaces of
equal length before scanning, which keeps character offsets valid for the
qualifier lookup.

Remaining misses are vocabulary gaps, not structural failures: analytes outside
the table (TSH, electrolytes, FEV1), washout subjects outside the class list
(peptic ulcer, PEG tube), and stages written without the word "stage".

### PRIOR_THERAPY vs WASHOUT

These two overlap constantly, and the line between them is what keeps both
honest:

> **WASHOUT** restricts *when* a therapy was given. **PRIOR_THERAPY** restricts
> *whether* it was given, or *how many* lines.

"Prior radiotherapy within 2 weeks of the start of study drug" is a washout
only — the patient becomes eligible by waiting. Emitting a treatment-history
predicate for it as well would double-count the criterion and make the trial
look permanently blocked. So a class that already produced a WASHOUT for the
same criterion is suppressed here, *unless* a line count or a treatment-naive
claim is also present, since those are history requirements regardless of any
window. This single rule took PRIOR_THERAPY precision from 0.719 to 0.788.

Three further distinctions:

- **`prior` is usually the preposition.** `prior to the first dose` is a
  window; `prior therapy` is a history claim. The compiler requires
  `\bprior\b(?!\s+to)`.
- **"No more than 3 prior lines" is a cap, not a denial.** It says the patient
  *has* had prior therapy. Reading the leading "no" as negation inverts the
  criterion, so the negation pattern excludes `no more/less/fewer than`.
- **Toxicity language cuts both ways.** "Unresolved toxicities from prior
  therapy" is a recovery requirement; "Grade 3 toxicity to a prior checkpoint
  inhibitor" is a treatment-history exclusion. The guard applies only when no
  specific therapy class is named.

`required` follows the same convention as BIOMARKER: it describes what the
criterion asserts about the patient, independent of inclusion/exclusion. Where
the splitter already flipped polarity on "must not have received X", that
negation is *not* read a second time — double-negating would make the predicate
assert the opposite of the sentence.

### WASHOUT design

A washout is only compiled when the thing whose date is needed can be **named**,
because evaluation is `last_date[class] + window`. A window that cannot be
attached to a lookup key falls through to FREE_TEXT rather than becoming a
predicate that can never be evaluated. Three distinctions do the work:

- **Half-lives are not computable.** `>= 5 half-lives or >= 42 days, whichever
  is longer` compiles on the 42 days and records `half_lives` and `whichever`;
  a criterion offering *only* half-lives does not compile at all.
- **Measurement recency is not a washout.** `Hb > 9.0 g/dL (within 28 days
  prior to randomization)` constrains data freshness, not patient state — no
  amount of waiting makes the patient eligible.
- **Treatment duration is not a window.** `a minimum of 12 weeks on continued
  pembrolizumab` and `completed 3 years adjuvant osimertinib` say how long
  therapy ran, not how long since it stopped.

Parent-header windows are inherited: `Any of the following within 6 months
before the first dose:` governs its children, which is what the `context` field
added in the splitter rewrite is for.

### Date arithmetic

`src/dates.py` does calendar arithmetic, not 30-day months. `6 months` from
31 Aug is 28 Feb, not 27 Feb; `31 Jan + 1 month` clamps to 28 Feb (29 Feb in a
leap year); `29 Feb + 1 year` clamps to 28 Feb. Payloads carry `amount`/`unit`
plus an `exact` flag marking whether the window is a fixed multiple of days
(days/weeks) or needs calendar handling (months/years). No third-party
dependency.

### The five clinical types

`src/onco.py` holds the histology, stage, and biomarker vocabulary. Four
distinctions carry most of the precision:

- **A named tumour is usually background, not a requirement.** "NSCLC" appears
  in most criteria of an NSCLC trial ("prior treatment for stage IIIB/IV
  NSCLC"), where it states no histology restriction. A generic term needs a
  diagnosis claim nearby; a *subtype* (squamous, adenocarcinoma, SCLC) is
  always a claim. This alone moved HISTOLOGY precision from 0.651 to 0.853.
- **Stage in a therapy clause is context.** "systemic treatment **for** stage
  IIIB/IV NSCLC" describes what the patient was treated for, not what the trial
  admits. STAGE precision 0.848 → 0.933.
- **Specific alterations outrank the generic noun.** "EGFR sensitizing
  mutations (Exon19del and/or L858R)" claims the two variants, not the word
  "mutations"; a gene list ("EGFR, ALK, ROS1, MET or RET mutations/fusions")
  shares one trailing alteration. Alteration windows stop at the next gene, so
  "KRAS G12C ... EGFR L858R" cannot cross-assign.
- **`MET` and `RET` are matched case-sensitively.** Under `re.I` they collide
  with the ordinary word "met", which appears constantly ("have met the
  criteria").

Stage ranges expand over an ordinal table where a bare endpoint spans its
substages, so `I-III` reaches IIIC and `IB-IIIB` yields IB, II, IIA, IIB, III,
IIIA, IIIB. Descriptive language maps only where it is unambiguous —
`metastatic` → IV, `locally advanced` → III, flagged with `from_descriptor`;
bare "advanced" spans III and IV and is left uncompiled.

`PERFORMANCE_STATUS` keeps the operator rather than folding it into a bound:
"ECOG > 1" in an exclusion asserts PS > 1, and storing `max_value = 1` would
invert it.

## Stage 3 results

The whole online path, on the 500-trial corpus with a stage IV EGFR-mutant
persona:

```
500 trials evaluated in 62 ms   (0.12 ms/trial)   0 model calls

  eligible_now          46
  eligible_on_date       4
  undetermined          20
  blocked              430
```

That is the 9.3 cost-and-latency number in its strongest form: **zero model
calls at query time**. All 15,135 predicates are Python comparisons against a
cached, precompiled corpus.

### Verdict semantics — a deliberate deviation

The spec defines MET as "the predicate is true", making the rule "all inclusion
criteria MET, no exclusion criteria MET". `evaluate.py` instead defines
**MET = the patient satisfies this criterion**, resolving polarity (inclusion
vs exclusion, `required`, `excluded`, textual negation) in one place where the
payload semantics are known. Aggregation becomes "every criterion MET".

The formulations are equivalent, but polarity applied in two layers has already
caused three bugs in this project. `is_inclusion` is still on every Criterion,
so the UI groups rows normally.

### Silence is not absence

The single most important rule in the evaluator, and the reason the
Undetermined bucket exists:

- a condition absent from the record is **UNDETERMINED**, not absent — unless
  the record explicitly rules it out (`negative_findings`)
- a gene with no result is **UNDETERMINED**, never "wild-type"
- a therapy class not listed is **UNDETERMINED** unless the history is marked
  exhaustive (`therapy_history_complete`); line counts require it outright
- a washout with no anchor date is **UNDETERMINED** — the anchor is never
  guessed — *except* where the record documents the therapy was never given,
  in which case there is nothing to wash out and the criterion is MET

### State precedence

`BLOCKED` > `UNDETERMINED` > `ELIGIBLE_ON_DATE` > `ELIGIBLE_NOW`. A trial the
patient can never enter must not be presented as "waiting", and among blockers
an IMMUTABLE one is reported ahead of a correctable one — it is why the trial
can never open, not merely why it is shut today.

### Extraction and the model chokepoint

`extract.py` has two paths producing the same `PatientRecord`:

- **`extract_rules()`** — deterministic, zero cost, offline. It reuses the
  vocabularies the compiler already uses: a report and a criterion speak the
  same clinical language, so `units.py`, `onco.py`, `conditions.py` and
  `drugs.py` all apply unchanged. This is what the demo runs.
- **`extract_llm()`** — one call through `llm.py`, filling only what the rules
  left empty. A rule-extracted value is never overwritten by the model.

`extract()` degrades rather than fails: with no key, no cache, or a rate-limit
error, it returns the rules result and the page still renders.

**Everything is free.** Default provider is the Gemini REST API called with
`urllib` — no SDK, so the project keeps its zero-dependency install. Total
budget is ~250 calls (1 per patient query, ~150-200 one-off for the 9.2
prompted baseline), which any free tier absorbs. `llm.py` caches every response
to disk keyed on a hash of (model, prompt), so **the demo never touches the
network** and reruns of the eval cost nothing. Set `GEMINI_API_KEY` to enable
the model path; nothing breaks without it.

Metric 9.4 is where free stops working — TREC 2022 is 50 patients x ~254
candidate trials, so criterion-level prompting is tens of thousands of calls.
The spec already marks it optional, and the deck stands on 9.1 and 9.2.

### One source of truth for the persona

The persona is its report text and nothing else; `load_persona()` runs the real
extractor over it. An earlier version kept a hand-written record alongside the
report, and the two drifted immediately — the fixture asserted negatives the
report never stated in recognisable form ("no pleural **or pericardial**
effusion" never contains the literal phrase "pleural effusion"). Deriving the
record from the text makes the golden file test the path the demo actually
runs.

### Golden file

`tests/test_golden.py` pins 50 fixed trials against the persona: state,
eligibility date, blocking reason, missing fields, and verdict counts. Run
before every demo rehearsal; regenerate deliberately with `--update`.

## Stage 4 — the UI

```bash
python3 ui/app.py        # -> http://localhost:8000
```

**Standard library only.** Flask is installed on this machine but a judge
cloning the repo may not have it, so the server is `http.server`. No install
step, nothing to go wrong on demo day. The compiled corpus loads once at
startup; a query is evaluation only.

Three screens, as the spec specifies:

1. **Paste box with a "Load sample patient" button.** The button is the primary
   path — the demo never depends on a file dialog or on typing.
2. **Results in four sections**, each trial a card with a criterion checklist.
   Rows are green (MET), amber (PENDING), grey (UNDETERMINED), red (NOT_MET),
   sorted worst-first so the reason a trial failed is the first thing visible.
   Clicking a state tile filters to that bucket.
3. **Click any row and the originating sentence highlights** in the report.
   `Result.used` records which patient field each verdict read, and
   `PatientRecord.spans()` maps that to character offsets — so clicking the
   washout row on the dated trial highlights the exact `pemetrexed` last-dose
   line the eligibility date was computed from.

The header carries the 9.3 number live: `500 trials · extract 39 ms ·
evaluate 59 ms · 0 model calls`.

The eligibility calendar (stage 6) and missing-data panel (stage 7) are already
present, since `aggregate.py` returns both. The missing-data headline counts the
**union** of trials the recommended tests unblock, not the largest single row —
the same trial usually needs several of them, so a max or a sum both overstate
the reach.

### A trial we never checked is not "eligible"

Two trials in the corpus compile to zero machine-checkable criteria — every
criterion is free text. They were being reported ELIGIBLE_NOW for *any* patient,
including a record with no clinical content, because nothing blocked them.
That is the most dishonest output the system could produce, so a trial with no
evaluable criteria is now UNDETERMINED with the reason *"no machine-checkable
criteria; needs manual review"*.

## Video

`deck/VIDEO_SCRIPT.md` — five minutes, timed to section 11 of the build spec,
with the exact words, the exact clicks, and a pre-flight checklist. Every trial
ID, date and figure in it is verified against the running app; re-run the
pre-flight after any code change, because the numbers move.

## Deck

`deck/eligibility-compiler.pptx` — 14 slides, regenerated with
`node deck/build.js`. `deck/eligibility-compiler.pdf` is the same deck
exported, for anywhere PowerPoint isn't available. Every figure on it is
reproducible from this repo.

Charts are **drawn with shapes, not embedded as OOXML chart parts.** Native
charts validated fine but Keynote silently dropped them, and with no PowerPoint
on the build machine there was no way to confirm they would survive. A blank
slide mid-demo is unrecoverable, so the deck carries no renderer dependency it
cannot verify.

`deck/qa.py` checks the built file numerically — every shape against slide
bounds, text-box overlap, and text overflow estimated from font metrics. It
caught 14 real defects (stat cards too short for 38pt numerals, the title
running under the stats column, three overflowing boxes) that a read-through
would not have.

Note for whoever presents it: **slide 9 (metric 9.2) marks the prompted
baseline as pending.** Fill it in by setting `GEMINI_API_KEY` and running
`eval/numeric_accuracy.py --prompted`, then update that one slide.

## Metric 9.2 — compiled vs prompted numeric accuracy

**146 hand-labelled criterion instances**, every criterion string verbatim from
the 500-trial corpus and carrying its NCT ID, so the set can be audited against
the source. Only the patient state is constructed.

```bash
python3 eval/numeric_accuracy.py               # compiled arm
python3 eval/numeric_accuracy.py --holdout     # the unbiased number
GEMINI_API_KEY=... python3 eval/numeric_accuracy.py --prompted
```

### The honest version of the number

The main set found **eight genuine bugs**, which were then fixed. That makes it
a regression suite, not an unbiased estimate — quoting its post-fix 100% as the
headline would be tuning on the test set.

`data/eval/numeric_holdout.py` holds **32 cases written after the fixes and run
exactly once**. That is the number to present:

| set | n | compiled | note |
|---|---|---|---|
| held-out | 32 | **100.0%** | written before running, run once |
| development | 146 | 100.0% | post-fix; a regression suite, not an estimate |

The prompted arm is built and ready; it needs `GEMINI_API_KEY` and ~150 cached
calls. **Report it with whatever it produces** — a small gap is still a result,
and the 9.3 cost ratio holds regardless.

### What the eval found

Eight bugs, none of which the unit tests caught, because unit tests check what
you thought to check:

1. **Exclusion polarity was never applied** to LAB, AGE, PERFORMANCE_STATUS,
   STAGE, BIOMARKER or PRIOR_THERAPY. Every exclusion criterion of those types
   evaluated backwards: a patient with a normal QTc was blocked, one with a
   prolonged QTc passed. This was live in the UI. Fixing it moved 10 trials
   between buckets on the demo persona.
2. **Floating point on ULN bounds.** `1.5 × 1.2` is `1.7999999999999998`, so a
   patient at exactly 1.8 failed a `<= 1.5 x ULN` bound — silent, and precisely
   on the boundary the protocol cares about.
3. **A conjunction compiled as a disjunction.** "AST **and** ALT <= 3x ULN"
   shared one predicate group, so a passing AST masked a failing ALT.
4. **`Long Form (ABBREV)` counted as two analytes**, which scrambled that
   grouping for "INR or PT".
5. **QTc in seconds never converted** — 0.485 s read as 0.485 ms.
6. **A documented "never received" was ignored** when the therapy list was
   otherwise empty.
7. **A parent class was emitted alongside its child** — "EGFR tyrosine kinase
   inhibitor" produced both `EGFR_TKI` and generic `TKI`, and the generic one
   abstained and dragged the criterion to UNDETERMINED.
8. **Two names for one concept** — `PRIOR_MALIGNANCY` in `drugs.py`,
   `SECOND_MALIGNANCY` in `conditions.py`. Unified.

Three of my own gold labels were also wrong, and are corrected in place with
the reasoning recorded in each case's `why` field.

### Fairness of the prompted arm

A handicapped baseline proves nothing, so the prompted arm gets exactly the
string the compiled arm gets, built by the same `render_patient()`; all four
verdicts defined including PENDING; the index date; and an explicit instruction
to show its arithmetic before answering, so it is free to reason. Temperature 0.

## Metric 9.5 — measurable differences from prior work

Slide 4 concedes that reasoning-based trial matching already exists, so the
differentiation has to be evidence rather than assertion. This is the evidence,
and it needs no API key and no network:

```bash
python3 eval/differentiation.py               # ~10s, 0 model calls
```

| property | measured | why a prompted matcher cannot just adopt it |
|---|---|---|
| determinism | 20 runs, **1 distinct output hash** | sampling; no cited system reports run-to-run variance at all |
| temporal answer | **2 trials dated** (25 Aug, 8 Sep 2026) | a class label does not carry a date |
| provenance | **75.6%** of verdicts resolve to a character span | the span is emitted by the evaluator, not generated beside the answer |
| abstention | **10.6%** abstained; top 4 tests resolve **340 criteria** | a model asked for a verdict returns one even from a silent note |

The hash covers every field of the payload except the timing block, which
varies by construction.

**Where this loses is printed by the same script**, and it belongs on the same
slide as the claims: TREC NDCG@10 0.3600 against TrialGPT's published 0.7252,
scope is one cancer type, and the compiled-vs-prompted numeric head-to-head
(9.2) has not been run. Until it has, "better at numeric criteria" is an
argument, not a result.

Provenance coverage was **36.1%** until documented negatives were given spans:
"no brain metastases" is the evidence a NOT_MET verdict rests on, and it was
not clickable. `PatientRecord.negative_spans` fixed that — 18 spans became 84.
The residue is genuinely non-locatable: therapy classes resolved from
`therapy_history_complete` rather than from any one sentence, and labs that
were never drawn.

## Metric 9.4 — ranking on TREC Clinical Trials 2022

**Report this honestly and do not lead with it.** The spec says so, and the
result bears it out.

```bash
python3 eval/ranking_benchmark.py --sweep     # ~70s, 0 model calls
python3 eval/retrieval_recall.py              # ~15s
```

50 topics, 12,682 candidate trials, ranked over TrialGPT's own retrieved pool
so only the *ranker* is compared:

| system | NDCG@10 (linear) | NDCG@10 (exp) | P@10 (eligible) | P@10 (relevant) |
|---|---|---|---|---|
| BM25 only | 0.3023 | 0.2737 | 0.1960 | 0.3680 |
| compiled predicates only | 0.0147 | 0.0107 | 0.0040 | 0.0380 |
| **hybrid (α = 0.7)** | **0.3600** | 0.3325 | **0.2580** | 0.4100 |
| TrialGPT (published) | 0.7252 | — | 0.6724 | — |

**We are at roughly half of TrialGPT.** Four caveats, all of which a
knowledgeable judge would raise unprompted:

1. TrialGPT reranks with an LLM at criterion level. This uses **zero model
   calls**, so it is a different class of system.
2. The published gain convention is unconfirmed from the shipped data, and NDCG
   moves materially between linear and exponential gain — both are reported.
3. Ranking runs over their pool, so retrieval is not being compared.
4. TREC topics are synthetic, ~600-character, and span all of medicine. This
   compiler's vocabulary is NSCLC-specific.

α = 0.7 was fixed before the run. The sweep below shows α = 0.3 scores slightly
higher (0.3665); **that is not quoted as the result**, because choosing it after
seeing the test set is the same error the 9.2 held-out split exists to avoid.

### The interesting finding

The compiled predicates are **worthless alone** (0.0147) yet adding them to BM25
lifts NDCG@10 by **+19%** and P@10 by **+32%** relative:

| α (1.0 = lexical only) | 1.0 | 0.9 | 0.8 | 0.7 | 0.5 | 0.3 | 0.0 |
|---|---|---|---|---|---|---|---|
| NDCG@10 | 0.3023 | 0.3301 | 0.3383 | 0.3600 | 0.3607 | 0.3665 | 0.0147 |
| P@10 | 0.1960 | 0.2280 | 0.2340 | 0.2580 | 0.2660 | 0.2740 | 0.0040 |

That is the labels' structure showing through: BM25 separates 0 from {1,2}
(topical relevance), predicates separate 2 from 1 (eligible vs excluded).
Neither does the other's job.

### Why the ceiling is where it is

The benchmark does not contain the inputs this system runs on. Across all 50
TREC notes, extraction recovers:

| field | found | per note |
|---|---|---|
| age | 49 | 0.98 |
| sex | 42 | 0.84 |
| labs | 18 | 0.36 |
| conditions | 16 | 0.32 |
| therapies | 3 | 0.06 |
| **stage** | **0** | 0.00 |
| **ECOG** | **0** | 0.00 |
| **biomarkers** | **0** | 0.00 |
| **dated therapies** | **0** | 0.00 |

Zero dated therapies means **not one washout predicate can resolve** — the
mechanism the whole system is built around never fires. The +32% P@10 above is
what age and sex alone buy. This is a finding about the benchmark, not an
excuse: TREC CT measures topical retrieval from narrative notes, and this
system compiles eligibility arithmetic from structured records.

## Retrieval recall

Recall of ELIGIBLE trials (qrels label 2) over an 11,604-trial corpus:

| system | R@10 | R@50 | R@100 | R@254 | R@500 | R@1000 |
|---|---|---|---|---|---|---|
| BM25 | 0.047 | 0.190 | 0.295 | 0.498 | 0.630 | 0.729 |
| **LSA** | **0.066** | **0.226** | **0.380** | **0.695** | **0.855** | **0.915** |
| hybrid (RRF) | 0.058 | 0.216 | 0.376 | 0.639 | 0.814 | 0.896 |

60 ms per query, 0 model calls.

**The fusion is not helping.** LSA alone beats the RRF hybrid at every cutoff,
because RRF averages in BM25's weaker ranking. The spec asked for BM25 + dense
fused; the honest reading of the measurement is that the dense arm carries it
and fusion costs about 6 points of R@254. Reported rather than quietly dropped.

Two things to be precise about:

- The dense arm is **TF-IDF + truncated SVD (LSA), not a neural sentence
  embedding**. It captures term co-occurrence, not meaning. TrialGPT's
  retrieval uses actual neural embeddings, so the arms are not equivalent.
- The corpus is the **union of TrialGPT's per-patient pools**, because TREC
  2021/2022 ship no `corpus.jsonl` (only SIGIR does). Recall against 11.6k
  already-surfaced trials is optimistic relative to the full registry and is
  **not comparable to a published retrieval figure**.

## Gold-set correction

Scoring WASHOUT surfaced that the hand labels disagreed with themselves: of ten
`prior malignancy within N years` criteria, eight carried WASH and two did not,
while four scan-recency windows had been labelled WASH. `eval/fix_gold_labels.py`
applies one rule (WASH iff a backward window attaches to a datable therapy,
procedure, or event) and documents every correction — 13 added, 4 removed. The
figures above are post-correction.

### Splitter rewrite

Criterion counts changed because the splitter was rewritten, so compile-rate
figures before and after are not comparable:

| | before | after |
|---|---|---|
| criteria (500 trials) | 14,510 | 13,202 |
| LAB_THRESHOLD predicates | 2,351 | 2,407 |

Fewer criteria, more predicates — the units got more faithful, not smaller.
Four changes:

1. **Continuations rejoined across blank lines.** A criterion's predicate often
   sits on a later line, indented under its marker, after a blank line
   (`ALT and AST` / *blank* / `<= 3.0 x ULN if no liver involvement`). Flushing
   on blank lines orphaned the threshold from its analyte. Continuation is now
   decided by indentation depth.
2. **Section headers matched robustly.** `Phase 1b Exclusion Criteria:` and
   `Exclusion Criteria (Part A)` failed an exact match and filed their
   exclusions as inclusions. Guarded against sentences *about* criteria
   (`Other inclusion/exclusion criteria may apply.`).
3. **Prose polarity.** 172 criteria stated as `Participants must not have X`
   inside inclusion sections are now filed as exclusions, with
   `polarity_flipped` set. `raw_text` is never rewritten.
4. **List headers absorbed as `context`, not emitted as criteria.** A header
   often carries the window governing its children (`Any of the following
   within 6 months before the first dose:`), which WASHOUT will need. 1,582
   criteria carry parent context.

The comma-splitting bundle exploder was **removed**: the compiler emits one
predicate per analyte from a single criterion, and text-level splitting was
lossy — it tore conditional variants apart and truncated Gilbert's carve-outs.

### Gold set

`data/eval/handread_gold.jsonl` is keyed by criterion **text**, not by position
in the split output. A splitter change therefore surfaces as unlabelled
criteria rather than silently misaligned labels. Re-run
`eval/migrate_gold.py` after any change to `split.py`; it exits non-zero and
writes nothing while criteria remain unlabelled.

## Deviations from the build spec

These are deliberate and driven by what the corpus actually contains.

**`compile_criterion` returns `list[Criterion]`, not one `Criterion`.**
9.1% of hand-read criteria need more than one predicate type, and a single
sentence routinely states several thresholds (`AST and ALT <= 2.5 x ULN` is two
predicates; `ANC >= 1.5, PLT >= 100, Hb >= 90 g/L` is three).

**`LAB_THRESHOLD.payload` carries four fields beyond the spec's
`analyte/operator/value/unit`:**

| field | why |
|---|---|
| `basis` | `absolute` \| `uln` \| `lln`. **37% of lab thresholds are ULN-relative** (`bilirubin <= 1.5 x ULN`). For these, `value` is a multiplier, resolved against the patient's institutional limit at evaluation, falling back to `units.REFERENCE_LIMITS`. Without this the type loses a third of its yield. |
| `raw_value`, `raw_unit` | pre-normalization values, kept for audit and UI display |
| `condition` | `liver_metastases` \| `no_liver_metastases` \| `gilberts`. Selects between alternative thresholds in one sentence (`<= 2.5 x ULN, or <= 5 x ULN if liver metastases`). |
| `group` | predicates sharing a group are OR'd. `creatinine <= 1.5 x ULN OR CrCl >= 40 mL/min` is one requirement with two routes; evaluating only one arm gives wrong answers. |

## Layout

```
data/raw/        ClinicalTrials.gov dumps + TrialGPT TREC cache (gitignored)
data/eval/       hand-read labels, personas
src/fetch.py     ClinicalTrials.gov v2 client
src/fetch_trec.py TrialGPT corpus download + parse verification
src/split.py     eligibility block -> criteria (with char offsets)
src/units.py     analyte normalization, unit table, reference limits
src/compile.py   criterion -> typed predicates
eval/            compile_rate.py, type_distribution.py, differentiation.py
tests/           62 tests
```

## Run

```bash
python3 src/fetch.py            # pull 500 NSCLC trials
python3 src/fetch_trec.py       # download + verify TREC cache
python3 eval/type_distribution.py
python3 eval/compile_rate.py
python3 -m pytest tests/ -q
```
