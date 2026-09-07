"""Metric 9.5 - the differences from prior work that can be measured here.

Slide 4 concedes that reasoning-based trial matching already exists. This
script produces the numbers behind the claim that the *architecture* differs,
using only what can be measured on this machine with no API key and no
network. Nothing here is a comparison against another system's outputs: where a
published figure is quoted it is labelled as published, and where this system
loses it says so.

    python3 eval/differentiation.py

The four properties measured are the four that follow from compiling rather
than prompting, and each is falsifiable:

  determinism   identical input -> byte-identical output, over N runs.
                A sampled model has no such guarantee, and no cited system
                reports run-to-run variance at all.
  dates         how many trials get a specific calendar date rather than a
                categorical "eligible in future" label.
  provenance    what fraction of verdicts carry a character span into the
                patient record, so a coordinator can check the source.
  abstention    how often the system declines to answer and names the test
                that would resolve it, rather than producing a verdict from
                a silent record.

The honest counterweight is printed last and is not optional.
"""

import hashlib
import json
import statistics
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "data" / "eval"))

from aggregate import (TrialState, assess_all, eligibility_calendar,  # noqa: E402
                       missing_data_panel)
from evaluate import Verdict  # noqa: E402
from loader import HISTORY_COMPLETE, load_corpus  # noqa: E402
from extract import extract_rules  # noqa: E402
from personas import PERSONAS  # noqa: E402
from service import assess_payload  # noqa: E402

RUNS = 20

# Published figures, quoted only with their source. Not re-measured here.
PUBLISHED = {
    "trialgpt_ndcg": ("0.7252", "TrialGPT, NIH 2024, TREC 2022"),
    "leach_calls": ("~950 LLM calls per patient", "Leach et al., arXiv 2512.08026"),
}


def rule(label=""):
    print(f"\n{'─' * 72}")
    if label:
        print(f"{label}\n")


def patient_for(key):
    d = PERSONAS[key]
    p = extract_rules(d["report"], d["index_date"])
    p.therapy_history_complete = bool(HISTORY_COMPLETE.search(d["report"]))
    return d, p


# ────────────────────────────────────────────────────── determinism ──

def measure_determinism(compiled, meta, d):
    """Same input, N times. Any difference at all is a failure."""
    digests, times = [], []
    for _ in range(RUNS):
        t = time.perf_counter()
        out = assess_payload(compiled, meta, d["report"], d["index_date"])
        times.append((time.perf_counter() - t) * 1000)
        # Timing varies by construction; everything else must not.
        out = {k: v for k, v in out.items() if k != "timing"}
        digests.append(hashlib.sha256(
            json.dumps(out, sort_keys=True).encode()).hexdigest())

    unique = set(digests)
    print(f"  runs                    {RUNS}")
    print(f"  distinct output hashes  {len(unique)}"
          f"{'   <- FAIL' if len(unique) != 1 else ''}")
    print(f"  sha256                  {digests[0][:32]}…")
    print(f"  latency ms              median {statistics.median(times):.0f}  "
          f"min {min(times):.0f}  max {max(times):.0f}")
    print("\n  A sampled language model gives no such guarantee, and none of "
          "the systems on\n  slide 4 report run-to-run variance. This is a "
          "property of compiling, not of\n  being careful.")
    return len(unique) == 1


# ──────────────────────────────────────────────────────────── dates ──

def measure_dates(assessments):
    """Specific calendar dates are a strictly stronger output than a label."""
    dated = [a for a in assessments if a.state is TrialState.ELIGIBLE_ON_DATE]
    cal = eligibility_calendar(assessments)
    horizon = max((c["date"] for c in cal), default=None)
    anchor_dates = {r.anchor_date for a in assessments for r in a.results
                    if r.anchor_date}

    print(f"  trials with a specific opening date   {len(dated)}")
    print(f"  distinct dates on the calendar        {len(cal)}")
    if cal:
        print(f"  furthest date computed                "
              f"{horizon.isoformat()}")
    print(f"  distinct anchor dates read from the note   {len(anchor_dates)}")
    for c in cal:
        print(f"    {c['date'].isoformat()}   {c['trials']} trial(s)   "
              f"{(c['reasons'][0] if c['reasons'] else '')[:44]}")
    print("\n  A four-class label ('could be eligible in future') tells a "
          "coordinator to\n  check back. A date tells them when. The date is "
          "calendar arithmetic over an\n  anchor that is on screen and "
          "checkable.")


# ─────────────────────────────────────────────────────── provenance ──

def measure_provenance(assessments, patient):
    """A verdict a coordinator cannot check is a verdict they must re-do.

    The denominator that matters is verdicts computed *from a patient field*.
    Plenty of criteria resolve without reading the record at all -- a washout
    on a drug class the patient never received is MET on an empty history --
    and counting those as missing provenance would flatter nothing and mislead
    everyone.
    """
    spans = dict(patient.spans())
    rows = [r for a in assessments for r in a.results
            if r.applicable and r.criterion.predicate_type != "FREE_TEXT"]
    consumed = [r for r in rows if (r.used or r.missing)]
    linked = [r for r in consumed
              if any(k in spans for k in (r.used or r.missing))]

    print(f"  evaluated predicates                  {len(rows)}")
    print(f"  ... that read a patient field         {len(consumed)}  "
          f"({100 * len(consumed) / max(len(rows), 1):.1f}%)")
    print(f"  ... of those, resolving to a span     {len(linked)}  "
          f"({100 * len(linked) / max(len(consumed), 1):.1f}%)")
    print(f"  distinct spans in the report          {len(spans)}")

    unlinked = Counter(k for r in consumed
                       for k in (r.used or r.missing) if k not in spans)
    if unlinked:
        print("\n  fields read but not locatable in the note "
              "(derived or defaulted):")
        for f, n in unlinked.most_common(5):
            print(f"    {f:<34} {n:>5}")

    print("\n  The span points into the *patient record*, not the trial text: "
          "it is the\n  evidence the verdict was computed from, so clicking a "
          "row shows the sentence\n  that produced it.")


# ──────────────────────────────────────────────────────── abstention ──

def measure_abstention(assessments):
    """Silence is not absence. Declining is a feature, if it names the gap."""
    verdicts = Counter(r.verdict for a in assessments for r in a.results
                       if r.applicable
                       and r.criterion.predicate_type != "FREE_TEXT")
    total = sum(verdicts.values())
    und = verdicts[Verdict.UNDETERMINED]
    panel = missing_data_panel(assessments)
    top4 = panel[:4]
    resolved = sum(r["criteria"] for r in top4)
    trials = len({t for r in top4 for t in r["trial_ids"]})

    print(f"  evaluated predicates                  {total}")
    for v in (Verdict.MET, Verdict.NOT_MET, Verdict.PENDING,
              Verdict.UNDETERMINED):
        print(f"    {v.value:<16}                  {verdicts[v]:>5}  "
              f"({100 * verdicts[v] / max(total, 1):4.1f}%)")
    print(f"\n  abstained rather than guessed         {und} "
          f"({100 * und / max(total, 1):.1f}%)")
    print(f"  named fields that would resolve them  {len(panel)}")
    print(f"  top 4 tests resolve                   {resolved} criteria "
          f"across {trials} trials")
    print("\n  A model asked 'does this patient meet this criterion' returns a "
          "verdict even\n  when the note never mentions the field. Here an "
          "unrecorded value is\n  UNDETERMINED and the missing field is named, "
          "which turns a gap into a\n  work order.")


# ────────────────────────────────────────────────────────────── cost ──

def measure_cost(compiled, assessments, ms):
    calls = 0
    trials = len(assessments)
    criteria = sum(len(v) for v in compiled.values())
    print(f"  model calls per patient query         {calls}")
    print(f"  trials evaluated                      {trials}")
    print(f"  compiled predicates evaluated         {criteria}")
    print(f"  wall clock                            {ms:.0f} ms")
    print(f"  marginal cost per query               $0.00")
    print(f"\n  A per-trial LLM matcher over the same corpus makes on the "
          f"order of one call\n  per trial per patient -- {trials} for this "
          f"query. Published: "
          f"{PUBLISHED['leach_calls'][0]}\n  ({PUBLISHED['leach_calls'][1]}). "
          f"The reasoning here happened once, offline, at\n  compile time; the "
          f"query is arithmetic.")


# ─────────────────────────────────────────────────── the other side ──

def print_counterweight():
    print("  Retrieval ranking is worse, and the deck says so.")
    print(f"    TREC 2022 NDCG@10   this system 0.3600 vs "
          f"{PUBLISHED['trialgpt_ndcg'][0]} published")
    print(f"                        ({PUBLISHED['trialgpt_ndcg'][1]})")
    print("    Those patient notes are ~600 characters with no lab values and "
          "no dates,\n    so no washout or lab predicate can fire. That "
          "explains the gap; it does\n    not erase it.")
    print("\n  Scope is one cancer type. Trial density varies several-fold "
          "across cancers,\n  so none of these numbers transfer without "
          "re-measuring.")
    print("\n  The head-to-head that would settle the numeric claim -- the "
          "prompted arm of\n  metric 9.2 -- has not been run. Until it has, "
          "'better at numeric criteria'\n  is an argument, not a result.")


def main():
    compiled, meta = load_corpus()
    d, patient = patient_for("maya_torres")

    t = time.perf_counter()
    assessments = assess_all(compiled, patient)
    ms = (time.perf_counter() - t) * 1000
    payload = assess_payload(compiled, meta, d["report"], d["index_date"])

    print(f"METRIC 9.5  measurable differences from prior work")
    print(f"corpus: {len(compiled)} trials, "
          f"{sum(len(v) for v in compiled.values())} compiled criteria")
    print(f"patient: {d['name']}, index date {d['index_date'].isoformat()}")

    rule("1. DETERMINISM  -- identical input, byte-identical output")
    ok = measure_determinism(compiled, meta, d)

    rule("2. DATES  -- a calendar, not a category")
    measure_dates(assessments)

    rule("3. PROVENANCE  -- every verdict points at its evidence")
    measure_provenance(assessments, patient)

    rule("4. ABSTENTION  -- silence is not absence")
    measure_abstention(assessments)

    rule("5. COST  -- the reasoning already happened")
    measure_cost(compiled, assessments, ms)

    rule("WHERE THIS LOSES")
    print_counterweight()
    print()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
