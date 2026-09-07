"""The JSON payload behind the interface, independent of how it is served.

`ui/app.py` (local http.server) and `deploy/api/assess.py` (Vercel serverless)
are both thin transports over this. Keeping the payload here means the demo
that gets recorded and the deployment that gets shared cannot drift apart.

Nothing here reads a file or writes one: the caller supplies the compiled
corpus. That is what lets the same code run on a read-only filesystem.
"""

import re
import time
from datetime import date, datetime, timedelta

from aggregate import (assess_all, eligibility_calendar, missing_data_headline,
                       missing_data_panel)
from evaluate import Verdict
from display import term
from extract import extract_rules

# A note whose treatment-history section is declared complete. Without this the
# evaluator treats an unlisted therapy class as UNDETERMINED rather than absent.
# (Mirrors loader.HISTORY_COMPLETE, duplicated so the query path does not have
# to import the corpus builder.)
HISTORY_COMPLETE = re.compile(
    r"treatment\s+history\s+is\s+complete|history\s+complete\s+as\s+listed|"
    r"no\s+other\s+prior\s+(?:therapy|treatment)", re.I)

# ── keeping the demo honest over time ────────────────────────────────────
# Every ISO date in a note, so the whole record can be moved as one piece.
_ISO_DATE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")


def parse_local_date(raw, *, window_days=2):
    """A client-supplied 'today', or None if it is absent or implausible.

    The server runs in UTC. A visitor in California opening this at 5pm sees
    UTC's tomorrow, and on a product whose whole claim is date accuracy that is
    not a rounding error. The browser knows the user's real local date, so it
    sends it.

    It is still only a hint: anything unparseable, or further than a couple of
    days from the server's own clock, is discarded rather than trusted. That
    covers every real timezone offset (max ±14h) while refusing a value that
    would move the demo somewhere arbitrary.
    """
    if not raw:
        return None
    try:
        d = datetime.strptime(str(raw)[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None
    return d if abs((d - date.today()).days) <= window_days else None


def rebase_persona(persona, today=None):
    """Shift every date in a persona so its index date lands on `today`.

    Eligibility arithmetic is entirely relative: a washout is anchored to a
    last-dose date and measured against the index date. Shifting every date by
    the same delta therefore preserves every verdict, every interval and every
    bucket count exactly -- while making the dates a visitor actually sees
    real ones.

    Without this the fixture rots in public. The persona is pinned to
    2026-08-14, so its headline trial reads "eligible from 25 Aug, in 11 days";
    once that day passes the site keeps saying it, and the product's central
    claim -- that it answers with a real date rather than a category -- is
    wrong for every visitor from then on. A demo that silently starts lying
    about the future is worse than one that admits it is a fixture.

    The stored fixture is untouched, so tests and the eval stay deterministic.
    """
    idx = persona["index_date"]
    target = today or date.today()
    delta = (target - idx).days
    if delta == 0:
        return dict(persona)

    def shift(m):
        d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        return (d + timedelta(days=delta)).isoformat()

    out = dict(persona)
    out["report"] = _ISO_DATE.sub(shift, persona["report"])
    out["index_date"] = target
    out["rebased_by_days"] = delta
    return out

# The day data/raw/nsclc_trials.jsonl was pulled from the registry API.
# Recruiting status goes stale; saying when it was true is the honest minimum.
CORPUS_SNAPSHOT = "2026-08-14"

VERDICT_CLASS = {
    Verdict.MET: "ok",                # green
    Verdict.PENDING: "pending",       # amber
    Verdict.UNDETERMINED: "unknown",  # grey
    Verdict.NOT_MET: "bad",           # red
}
ROW_ORDER = {Verdict.NOT_MET: 0, Verdict.PENDING: 1,
             Verdict.UNDETERMINED: 2, Verdict.MET: 3}


KIND_SUFFIX = {"date": "date", "comorbidity": "status", "biomarker": "test",
               "condition": "status"}


def _field_label(field):
    """'lab:QTC' -> 'QTc';  'date:TOXICITY' -> 'toxicity date'."""
    kind, _, rest = field.partition(":") if ":" in field else ("", "", field)
    name = term(rest or field)
    if kind == "therapy":
        return f"prior {name}"
    suffix = KIND_SUFFIX.get(kind)
    if not suffix:
        return name
    # "toxicity date" reads fine; "hospitalization for infection date" does not.
    return f"{suffix} of {name}" if " " in name else f"{name} {suffix}"


def _rows(assessment, spans):
    out = []
    for r in assessment.results:
        if r.criterion.predicate_type == "FREE_TEXT" or not r.applicable:
            continue
        # Which part of the report to highlight when this row is clicked.
        highlight = [spans[k] for k in (r.used or r.missing) if k in spans]
        out.append({
            "verdict": r.verdict.value,
            "cls": VERDICT_CLASS[r.verdict],
            "type": r.criterion.predicate_type,
            "inclusion": r.criterion.is_inclusion,
            "reason": r.reason,
            "raw_text": r.criterion.raw_text,
            "eligible_date": r.eligible_date.isoformat() if r.eligible_date else None,
            "anchor_date": r.anchor_date.isoformat() if r.anchor_date else None,
            "assumed": list(r.assumed),
            "missing": list(r.missing),
            "spans": highlight,
        })
    out.sort(key=lambda x: ROW_ORDER[Verdict(x["verdict"])])
    return out


def assess_payload(compiled, meta, report, index_date):
    t0 = time.time()
    patient = extract_rules(report, index_date)
    patient.therapy_history_complete = bool(HISTORY_COMPLETE.search(report))
    t_extract = time.time() - t0

    t1 = time.time()
    assessments = assess_all(compiled, patient)
    t_eval = time.time() - t1

    spans = dict(patient.spans())
    trials = []
    for a in assessments:
        m = meta.get(a.trial_id, {})
        loc = (m.get("locations") or [{}])[0]
        trials.append({
            "id": a.trial_id,
            "title": m.get("title", ""),
            "phase": ", ".join(m.get("phases", []) or []),
            "sponsor": m.get("sponsor"),
            "site": " ".join(x for x in (loc.get("city"), loc.get("state"),
                                         loc.get("country")) if x),
            "state": a.state.value,
            "eligible_date": a.eligible_date.isoformat() if a.eligible_date else None,
            "blocking_reason": a.blocking_reason,
            "counts": {v.value: n for v, n in a.counts.items()},
            "rows": _rows(a, spans),
        })

    return {
        "patient": {
            "report": report,
            "index_date": index_date.isoformat(),
            "age": patient.age.value if patient.age else None,
            "sex": patient.sex.value if patient.sex else None,
            "histology": patient.histology.value if patient.histology else None,
            # display-ready: "NSCLC_SQUAMOUS" -> "squamous NSCLC"
            "histology_label": term(patient.histology.value) if patient.histology else None,
            "stage": patient.stage.value if patient.stage else None,
            "ecog": patient.ecog.value if patient.ecog else None,
            "biomarkers": [f"{b.gene} {b.alteration}" for b in patient.biomarkers],
            "labs": len(patient.labs),
            "spans": {k: list(v) for k, v in spans.items()},
        },
        "trials": trials,
        "calendar": [
            {"date": c["date"].isoformat(), "trials": c["trials"],
             "reason": c["reasons"][0] if c["reasons"] else ""}
            for c in eligibility_calendar(assessments)
        ],
        "missing": [
            {**{k: v for k, v in r.items() if k != "trial_ids"},
             # One vocabulary, defined once in display.py. The browser should
             # not need to know that QTC is written QTc.
             "label": _field_label(r["field"])}
            for r in missing_data_panel(assessments, top=10)
        ],
        "source": {
            # Provenance, stated in the interface rather than only the README:
            # a trial list with no snapshot date invites a reader to assume it
            # is live, and this one is not.
            "registry": "ClinicalTrials.gov",
            "url": "https://clinicaltrials.gov",
            "snapshot": CORPUS_SNAPSHOT,
            "trials": len(assessments),
        },
        "missing_headline": missing_data_headline(
            missing_data_panel(assessments, top=4)),
        "timing": {
            "extract_ms": round(t_extract * 1000, 1),
            "evaluate_ms": round(t_eval * 1000, 1),
            "total_ms": round((time.time() - t0) * 1000, 1),
            "trials": len(assessments),
            "model_calls": 0,
        },
    }
