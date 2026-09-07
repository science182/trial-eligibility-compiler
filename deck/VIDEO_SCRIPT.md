# Five-minute video script

Timing follows section 11 of the build spec. **Rehearse at least three times
against the actual running system**, and run the pre-flight below each time.

Every trial ID and figure here was verified against the running app. **Dates
are not fixed**: the demo patient is rebased to today on every page load, so
run the pre-flight and read dates off the screen. Counts, intervals and trial
IDs are stable.

---

## Pre-flight (do this before every rehearsal and before the take)

```bash
cd trialcompiler
python3 -m pytest tests/ -q          # must be 389 passed
python3 src/loader.py                # rebuild the predicate cache
python3 deck/figures.py              # re-derive the deck's dates from today
cd deck && node build.js && cd ..    # rebuild the deck with those dates
python3 ui/app.py 8000               # leave running
```

> **Dates in this script are examples, not constants.** The demo patient is
> rebased to *today* every time the page loads, so the trial that opens
> "in eleven days" lands on a different calendar date each day you rehearse.
> The **intervals** never move: 11 days and 25 days, a 4-week washout.
> Read every date off the screen; say the intervals from memory.

Then in the browser, **before recording starts**:

1. Open `http://localhost:8000` at a window width of **1400px or wider**
   (below 860px the list stacks above the detail pane instead of beside it).
2. Press **Match 500 trials** once, let it finish, then reload. The first query
   in a fresh process runs ~2x slow; this warms it so the take shows a true
   number.
3. Leave the page on the intake screen, showing the upload panel. You will
   click **Use the test document** on camera — do not pre-load it.
4. Have the deck open in a second window, on **slide 2**.
5. Quit anything else heavy. Query time roughly triples under CPU contention.

Checklist — all eight must be true or stop and fix:

- [ ] `389 passed`
- [ ] Deck slide 6 shows the same two dates the app does (both in the future)
- [ ] Header reads **0 model calls** after a query
- [ ] Count chips read **2 / 42 / 35 / 421**, in that order
- [ ] **Use the test document** loads the note; **Match 500 trials** runs it
- [ ] `⌘K` opens the palette; typing `Dato-DXd` finds NCT06357533
- [ ] The work-order line reads **Order 4 tests to resolve 340 criteria across 220 trials**
- [ ] Sites read as `Birmingham, AL` / `Guangzhou, China` — not raw registry strings
- [ ] Network cable can be unplugged and the demo still works (it never
      touches the network)

---

## 0:00 – 0:45  ·  The demo, cold

**Screen:** the app, intake state — a drop zone for a note, and one test
document.

> "This is a coordinator's screen. It takes an oncology note — drop your own,
> or use the test document."

**Action:** click **Use the test document**. The note appears; it is a
64-year-old woman with stage IV lung adenocarcinoma.

> "Sixty-four-year-old woman, stage four lung adenocarcinoma. Five hundred
> currently-recruiting lung cancer trials on the other side."

**Action:** click **Match 500 trials**.

**Then say nothing.** Let it render — about a tenth of a second. The silence
is the point; resist filling it.

> "Five hundred trials. About a tenth of a second. Zero calls to a language
> model."

*(Point at the top right: `500 trials · ~65 ms` and the green `0 model calls`.)*

> "And it leads with the thing it can do that a label cannot: two of those
> trials aren't blocked. They open on a date."

*(The headline reads two dates — today they are `16 Sep · 30 Sep 2026`, and they move with the calendar. Read what is on screen.)*

**Action:** point at the pale line under the counts — don't click it yet.

> "And where the note is silent, it doesn't guess. It tells you what to order:
> four tests resolve three hundred and forty criteria across two hundred and
> twenty trials."

That line is the abstention claim from slide 6, visible in the product. Ten
seconds, and it pre-earns the argument you make at 3:00.

The millisecond figure moves with machine load. Measured on a quiet machine
it is 65 ms median (p99 81 ms); with a browser and a second server competing
for CPU it reached 355 ms. Say "about a tenth of a second", let the header
speak for itself, and **never read a number the screen contradicts.**

---

## 0:45 – 1:30  ·  Why this matters

**Screen:** switch to the deck, **slide 2**.

> "Fewer than five percent of adult cancer patients enrol in a trial. When you
> ask why not, fifty-six percent of the time the answer is that no suitable
> trial was available at their treatment location, and twenty-two percent of
> the time the criteria were too restrictive.
>
> Meanwhile twenty to forty percent of cancer trials fail to hit their
> enrolment targets and terminate early. Both sides of this market are starved
> at once.
>
> The reason is that eligibility criteria are prose. Written for a human
> coordinator to read by hand, one trial at a time."

**Optional, and the first thing to cut** — slide 3. The prior-work beat at 3:00 now
owns this time:

> "A single criterion can carry four different kinds of arithmetic: a
> conjunction, a threshold relative to a lab's own reference range, a
> conditional variant, and units that don't match the patient's chart."

---

## 1:30 – 3:00  ·  Provenance, then the date

Back to the app. **This is the most important ninety seconds of the video.**

### A blocked trial (≈40s)

**Action:** press **⌘K**, type `Dato-DXd`, press **Enter**. That lands on
**NCT06357533** — *Phase III, Open-label, Study of First-line Dato-DXd* — and
filters the list to the 25 trials ruled out for the same reason.

Rehearse this; it is two keystrokes and it fails loudly if you mistype.

> "This is a Phase III trial, and this patient cannot enter it. One line
> tells you why."

*(Point at the red reason: **EGFR mutation present, must be absent**.)*

**Action:** click the red **BIOMARKER** row.

> "Click the row, and the exact sentence in her report highlights. The trial
> requires absence of sensitising EGFR mutations. Her NGS report shows an EGFR
> exon 19 deletion. Nothing here is a similarity score — it's a citation."

*(The source note sits below the criteria in the same pane; `EGFR exon 19 deletion` highlights in yellow and scrolls itself into view.)*

### The dated trial (≈50s)

**Action:** press **Esc** to clear the filter, then click the first row —
**NCT06946927**, already at the top of the list.

> "Now the interesting bucket. Two trials aren't blocked at all — they're
> just early."

*(Point at the teal badge: **Eligible from 16 Sep 2026 — in 11 days**. The date shifts daily; the eleven days does not.)*

> "This one has a four-week washout on prior chemotherapy, and her last dose of
> carboplatin-pemetrexed is right here."

*(Read the last-dose date off the note. It moves with the calendar; the
four-week window does not.)*

**Action:** click the teal **WASHOUT** row. It is the only row above the fold —
*Already satisfied* is collapsed by default, so the source note is on screen
without scrolling.

> "Same mechanism — that's the last-dose line it computed from. Four weeks
> from that date is the date on the badge. She's not ineligible. She's
> eligible in eleven days.
>
> That date came out of Python, not a language model. Every washout is
> calendar arithmetic — six months from the 31st of August is the 28th of
> February, and a leap year moves it."

**If time is tight, cut the second dated trial (NCT06281678, the later of the two).
Do not cut the click-to-highlight.**

---

## 3:00 – 3:30  ·  Against prior work

**Screen:** deck, **slide 4**. Move through this one quickly — its whole job is
to stop a judge thinking you are claiming more than you are.

> "Reasoning-based trial matching already exists. TrialGPT at the NIH does
> criterion-level eligibility with explanations. I'm not claiming to have
> invented the task."

**Screen:** **slide 6**. Slow down here.

> "What's different is architectural, and I measured all four.
>
> It's deterministic — twenty runs of that whole query, one hash. A sampled
> model gives you no such guarantee, and none of these systems report
> run-to-run variance at all.
>
> It answers with a date instead of a category. You saw that.
>
> Three quarters of verdicts click back to the sentence they came from.
>
> And when the note is silent it abstains and names the test — those four
> tests resolve three hundred and forty criteria."

*(Point at the red strip.)*

> "And it's worse at retrieval ranking than TrialGPT. That's on the same slide
> as the claims, on purpose."

---

## 3:30 – 4:20  ·  The numbers

Brisk from here. Four slides, roughly twelve seconds each.

**Screen:** deck, **slide 8**.

> "Two measurements. First: how much of eligibility prose is actually
> deterministic? Sixty percent of criteria compile to an executable predicate.
> Nobody has published that number. The remaining forty percent is genuinely
> free text and goes to the model."

**Screen:** **slide 9**.

> "Second, and this is the headline. A hundred and forty-six hand-labelled
> criterion instances, every string taken verbatim from the corpus.
>
> On thirty-two held-out cases — written after the system was frozen, run
> once — the compiled path made no errors. Unit conversions, ULN-relative
> bounds, calendar months, month-end clamping, leap years."

**→ If you have run the prompted arm**, say the real comparison here:

> "The same model, given the same criterion and the same patient, prompted for
> a verdict directly, scored ___."

**→ If you have not run it**, say this instead and move on. Do not imply a
result you do not have:

> "The prompted baseline is built and fairness-audited, and it is the one
> number I don't have yet."

**Then, regardless —** slide 10:

> "What I can tell you is what building the eval did. It found eight real
> bugs before it produced a single chart, and none of them had been caught by
> three hundred and sixty-eight unit tests. Every exclusion criterion of six
> types was evaluating backwards — a patient with a normal QTc was being
> blocked. That was live in the interface I just showed you."

**Screen:** **slide 11**.

> "And the cost. Zero model calls per query, because all the reasoning happened
> once, offline. The comparable published pipeline makes about nine hundred and
> fifty calls per patient."

---

## 4:20 – 5:00  ·  Limitations

**Screen:** **slide 14**. **Do not cut this.**

> "What this doesn't do.
>
> Extraction errors propagate — mitigated by putting a character span on every
> field and by abstaining rather than guessing. Recruiting status on the
> registry is frequently stale, so contact details are for verification, not
> booking. Computed dates depend on a last-dose date that reports often state
> imprecisely or not at all, which is why the anchor is always on screen.
>
> On the public TREC benchmark this ranks at about half of TrialGPT's published
> figure. I'm reporting that rather than hiding it. The reason is instructive:
> those patient notes are six hundred characters and contain zero lab dates, so
> not one washout predicate can fire. The benchmark doesn't contain the inputs
> this system runs on.
>
> The trials are a fixed snapshot of ClinicalTrials.gov, not a live feed, and
> recruiting status goes stale fast. Every trial in the interface links straight
> to its registry record, and the snapshot date is on screen, so nothing here
> asks you to take the trial list on faith.
>
> This is decision support for coordinators and clinicians. It is not
> patient-facing, it makes no treatment recommendation, and it is lung cancer
> only — trial density varies several-fold across cancer types, so none of
> these numbers transfer without re-measuring."

**Close on slide 15.**

> "Sixty percent of eligibility criteria compile. No errors on held-out numeric
> criteria. Zero model calls per query. And an evaluation that found eight
> bugs before it drew a chart."

---

## Recovery lines

Rehearse these too. Something will go wrong once.

| If | Say |
|---|---|
| Render is slow | "It's re-warming the cache — normally this is about a tenth of a second." |
| Wrong trial opens | "Not that one —" and use ⌘K. Don't scroll. |
| ⌘K doesn't open | Click the `⌘K search trials` control in the header instead. |
| Counts in a different order | They read 2 / 42 / 35 / 421 — dated first, matching the headline. |
| Highlight doesn't fire | Click the row again. The span is there; the click may have landed on the card. |
| Counts differ from 42/2/35/421 | Read what's on screen. Never read the script's number over a different one. |
| App won't load | Cut to the deck and narrate slides 7 and 12. The deck stands alone. |

## Things not to say

- **Don't claim to have invented reasoning-based trial matching.** Slide 4
  exists to pre-empt exactly that question.
- **Don't quote the 146-case score as the headline.** The held-out 32 is the
  honest number.
- **Don't call the retrieval "neural embeddings."** It is TF-IDF plus SVD.
- **Don't say "100% accurate."** Say "no errors on thirty-two held-out
  criteria" — the interval on 32 cases is wide and a judge may know that.
