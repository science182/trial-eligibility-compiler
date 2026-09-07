"""Metric 9.2 — compiled vs prompted numeric criterion accuracy. The headline.

Two systems, one labelled set, identical inputs:

  compiled   split -> compile -> evaluate. Pure Python, no model.
  prompted   the same base model, given the same criterion text and the same
             patient state, asked for the verdict directly.

FAIRNESS. The prompted arm is not a strawman:
  - it receives exactly the string the compiled arm receives, built by the
    same `render_patient()`;
  - the four verdicts are defined for it in full, including PENDING and the
    rule that absence of data means UNDETERMINED;
  - it is told the index date and asked to show its arithmetic before
    answering, so it is free to reason;
  - temperature 0, and the answer is taken from a final structured line.

A baseline that is handicapped proves nothing, so anything that would make the
model look worse than it is has been deliberately avoided.

    python3 eval/numeric_accuracy.py              # compiled arm only
    GEMINI_API_KEY=... python3 eval/numeric_accuracy.py --prompted
"""

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "data" / "eval"))

from compile import compile_criterion  # noqa: E402
from evaluate import Verdict, evaluate_criterion  # noqa: E402
from numeric_cases import CASES, IDX  # noqa: E402
from patient import LabValue, PatientRecord, PriorTherapy, Sourced  # noqa: E402
from split import RawCriterion  # noqa: E402
from units import UnitError, to_canonical  # noqa: E402

RESULTS = ROOT / "data" / "eval" / "numeric_accuracy.json"


def _d(s):
    return datetime.strptime(s, "%Y-%m-%d").date()


# ─────────────────────────────────────────── build the patient ──

def build_patient(case):
    spec = case["patient"]
    idx = _d(spec.get("index") or case.get("index") or IDX)
    p = PatientRecord(index_date=idx)

    for analyte, (val, unit) in (spec.get("labs") or {}).items():
        try:
            v, u = to_canonical(analyte, val, unit)
        except UnitError:
            v, u = val, unit
        p.labs[analyte] = LabValue(analyte=analyte, value=v, unit=u,
                                   uln=(spec.get("uln") or {}).get(analyte))
    if "age" in spec:
        p.age = Sourced(spec["age"])
    for c in spec.get("conditions") or []:
        p.comorbidities.append(Sourced(c))
    p.negative_findings |= set(spec.get("no_conditions") or [])
    p.negative_findings |= set(spec.get("no_therapy") or [])
    for cls, d in (spec.get("last_dose") or {}).items():
        p.last_dose_dates[cls] = _d(d)
    for ev, d in (spec.get("event") or {}).items():
        p.event_dates[ev] = _d(d)

    if "lines" in spec:
        for i in range(spec["lines"]):
            p.prior_therapies.append(
                PriorTherapy(drug_class="CHEMOTHERAPY", line=i + 1,
                             progressed=spec.get("progressed")))
    for cls in spec.get("classes") or []:
        p.prior_therapies.append(
            PriorTherapy(drug_class=cls, line=len(p.prior_therapies) + 1,
                         progressed=spec.get("progressed")))
    p.therapy_history_complete = bool(spec.get("complete"))
    return p


UNIT_SHOWN = {"": "", None: ""}


def render_patient(case, p):
    """The patient state, as prose. BOTH arms are scored on exactly this."""
    spec = case["patient"]
    lines = [f"Index date (today): {p.index_date.isoformat()}"]

    for analyte, (val, unit) in (spec.get("labs") or {}).items():
        uln = (spec.get("uln") or {}).get(analyte)
        u = f" {unit}" if unit else ""
        extra = f" (institutional ULN {uln} for this analyte)" if uln else ""
        lines.append(f"{analyte}: {val}{u}{extra}")
    if not (spec.get("labs") or {}):
        lines.append("No laboratory values reported.")

    if "age" in spec:
        lines.append(f"Age: {spec['age']} years")
    for c in spec.get("conditions") or []:
        lines.append(f"Condition present: {c}")
    for c in spec.get("no_conditions") or []:
        lines.append(f"Condition documented ABSENT: {c}")
    for cls, d in (spec.get("last_dose") or {}).items():
        lines.append(f"Last dose of {cls}: {d}")
    for ev, d in (spec.get("event") or {}).items():
        lines.append(f"Date of {ev}: {d}")
    for cls in spec.get("no_therapy") or []:
        lines.append(f"Documented as NEVER received: {cls}")
    if "lines" in spec:
        lines.append(f"Number of prior lines of systemic therapy: {spec['lines']}")
    for cls in spec.get("classes") or []:
        lines.append(f"Prior therapy class received: {cls}")
    if spec.get("progressed"):
        lines.append("Progressed on the most recent prior therapy: yes")
    lines.append("Treatment history is stated to be complete and exhaustive: "
                 + ("yes" if spec.get("complete") else "no"))
    return "\n".join(lines)


# ───────────────────────────────────────────── compiled arm ──

def run_compiled(case):
    p = build_patient(case)
    raw = RawCriterion(trial_id=case["trial"], raw_text=case["text"],
                       is_inclusion=case["incl"], start=0, end=len(case["text"]))
    # 9.2 measures accuracy ON THE PREDICATE TYPE UNDER TEST. A criterion may
    # also mention a stage or a comorbidity; those belong to other metrics and
    # scoring them here would measure something else.
    crits = [c for c in compile_criterion(raw)
             if c.compiled and c.predicate_type == case["type"]]
    if not crits:
        # Nothing of this type compiled: the system abstains rather than guess.
        return "undetermined", None, "no predicate compiled"
    res = evaluate_criterion(crits, p)
    d = res.eligible_date.isoformat() if res.eligible_date else None
    return res.verdict.value, d, res.reason


# ───────────────────────────────────────────── prompted arm ──

PROMPT = """You are evaluating one clinical trial eligibility criterion \
against one patient.

CRITERION (verbatim from the trial protocol):
"{text}"

This criterion appears in the trial's {section} criteria.

PATIENT STATE:
{patient}

Decide which ONE verdict applies. Definitions:

- MET: the patient satisfies this criterion. For an EXCLUSION criterion this \
means the excluded thing is NOT true of the patient.
- NOT_MET: the patient violates this criterion. For an EXCLUSION criterion \
this means the excluded thing IS true of the patient.
- PENDING: the patient does not satisfy it today, but will satisfy it on a \
specific future date purely by waiting (for example a washout window that has \
not yet elapsed). Give that date.
- UNDETERMINED: the patient state does not contain the information needed to \
decide. Do not guess or assume a normal value.

Work carefully. Convert units where the criterion and the patient use \
different ones. Use calendar arithmetic for months and years, not 30-day \
approximations. Treat >= and <= as inclusive and > and < as strict.

Show your working, then end with exactly one line in this form:

VERDICT: <MET|NOT_MET|PENDING|UNDETERMINED>
DATE: <YYYY-MM-DD or NONE>
"""

VERDICT_RE = re.compile(r"VERDICT:\s*([A-Z_]+)", re.I)
DATE_RE = re.compile(r"DATE:\s*(\d{4}-\d{2}-\d{2}|NONE)", re.I)


def run_prompted(case, model=None):
    from llm import complete
    p = build_patient(case)
    prompt = PROMPT.format(text=case["text"],
                           section="inclusion" if case["incl"] else "exclusion",
                           patient=render_patient(case, p))
    out = complete(prompt, model=model, temperature=0.0)
    m = VERDICT_RE.search(out)
    verdict = (m.group(1).lower() if m else "unparsed")
    dm = DATE_RE.search(out)
    d = dm.group(1) if dm and dm.group(1).upper() != "NONE" else None
    return verdict, d, out.strip().splitlines()[-3:]


# ──────────────────────────────────────────────── scoring ──

def score(rows, key):
    ok = sum(1 for r in rows if r[key] == r["gold"])
    return ok, len(rows), (ok / len(rows) if rows else 0.0)


def table(rows, arms, group_fn, title, min_n=1):
    groups = defaultdict(list)
    for r in rows:
        for g in group_fn(r):
            groups[g].append(r)
    print(f"\n{title}")
    head = f"{'':<22}{'n':>5}" + "".join(f"{a:>12}" for a in arms)
    print(head)
    print("-" * len(head))
    for g, rs in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        if len(rs) < min_n:
            continue
        cells = "".join(f"{score(rs, a)[2] * 100:>11.1f}%" for a in arms)
        print(f"{g:<22}{len(rs):>5}{cells}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prompted", action="store_true",
                    help="also run the model baseline (needs GEMINI_API_KEY)")
    ap.add_argument("--model", default=None)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--holdout", action="store_true",
                    help="run the held-out set instead (the unbiased number)")
    args = ap.parse_args()

    if args.holdout:
        from numeric_holdout import HOLDOUT
        cases = HOLDOUT
    else:
        cases = CASES
    cases = cases[:args.limit] if args.limit else cases
    rows = []

    for c in cases:
        v, d, why = run_compiled(c)
        rows.append({"id": c["id"], "type": c["type"], "tags": c["tags"],
                     "gold": c["gold"], "gold_date": c.get("expect_date"),
                     "compiled": v, "compiled_date": d, "compiled_why": why})

    arms = ["compiled"]

    if args.prompted:
        import llm
        if not llm.available():
            print("GEMINI_API_KEY not set — cannot run the prompted arm.\n"
                  "The compiled arm below still runs; set the key and re-run\n"
                  "with --prompted to fill in the comparison.\n")
        else:
            arms.append("prompted")
            print(f"running prompted arm over {len(cases)} cases "
                  f"(cached responses are free) ...", flush=True)
            for i, (c, r) in enumerate(zip(cases, rows), 1):
                try:
                    v, d, tail = run_prompted(c, args.model)
                except Exception as e:                       # noqa: BLE001
                    v, d, tail = "error", None, [str(e)[:120]]
                r["prompted"], r["prompted_date"] = v, d
                if i % 25 == 0:
                    print(f"  {i}/{len(cases)}", flush=True)
            print(f"  model calls: {llm.LOG.summary()}")

    # ── report ──
    print("\n" + "=" * 62)
    print("METRIC 9.2  compiled vs prompted numeric criterion accuracy")
    print("=" * 62)
    print(f"labelled criterion instances: {len(rows)}")
    print("criterion text: verbatim from the 500-trial NSCLC corpus")

    print(f"\n{'':<22}{'n':>5}" + "".join(f"{a:>12}" for a in arms))
    print("-" * (27 + 12 * len(arms)))
    cells = "".join(f"{score(rows, a)[2] * 100:>11.1f}%" for a in arms)
    print(f"{'OVERALL':<22}{len(rows):>5}{cells}")

    table(rows, arms, lambda r: [r["type"]], "By predicate type")
    table(rows, arms, lambda r: r["tags"],
          "By what the case tests (the interesting breakdown)", min_n=3)

    # date accuracy on PENDING cases
    pend = [r for r in rows if r["gold"] == "pending"]
    if pend:
        print("\nEligibility-date accuracy on PENDING cases")
        print(f"{'':<22}{'n':>5}" + "".join(f"{a:>12}" for a in arms))
        print("-" * (27 + 12 * len(arms)))
        cs = ""
        for a in arms:
            ok = sum(1 for r in pend
                     if r.get(f"{a}_date") and r[f"{a}_date"] == r["gold_date"])
            cs += f"{ok / len(pend) * 100:>11.1f}%"
        print(f"{'exact date correct':<22}{len(pend):>5}{cs}")

    # failures, so they can be inspected rather than hidden
    bad = [r for r in rows if r["compiled"] != r["gold"]]
    if bad:
        print(f"\ncompiled-path failures ({len(bad)}):")
        for r in bad[:20]:
            print(f"  {r['id']:<10} gold={r['gold']:<13}got={r['compiled']:<13}"
                  f"{r['compiled_why'][:44]}")

    RESULTS.write_text(json.dumps(rows, indent=1) + "\n")
    print(f"\nper-case results -> {RESULTS}")


if __name__ == "__main__":
    main()
