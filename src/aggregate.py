"""Criterion verdicts -> the four trial states, with dates.

    ELIGIBLE_NOW      every criterion satisfied
    ELIGIBLE_ON_DATE  otherwise satisfied, blocked only by temporal criteria;
                      reports max(pending dates) and names the blocker
    UNDETERMINED      no hard block, but data is missing
    BLOCKED           at least one IMMUTABLE criterion not satisfied

Order matters: a hard block outranks missing data, which outranks a washout.
A trial the patient can never enter must not be presented as "waiting".
"""

from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Optional

from compile import Mutability
from evaluate import Verdict, evaluate_criterion


class TrialState(Enum):
    ELIGIBLE_NOW = "eligible_now"
    ELIGIBLE_ON_DATE = "eligible_on_date"
    UNDETERMINED = "undetermined"
    BLOCKED = "blocked"


@dataclass
class TrialAssessment:
    trial_id: str
    state: TrialState
    results: list = field(default_factory=list)     # every Result, for the UI
    eligible_date: Optional[date] = None
    blocking_reason: str = ""                       # one line
    blocking_result: object = None
    missing_fields: tuple = ()

    @property
    def counts(self):
        return Counter(r.verdict for r in self.results)


def _group_by_source(criteria):
    """Predicates compiled from the same source sentence belong together."""
    groups = {}
    for c in criteria:
        groups.setdefault((c.start, c.end, c.raw_text), []).append(c)
    return list(groups.values())


def assess_trial(trial_id, criteria, patient):
    """Evaluate every compiled criterion of one trial and pick a state."""
    results = []
    for group in _group_by_source(criteria):
        r = evaluate_criterion(group, patient)
        if r is not None:
            results.append(r)

    evaluable = [r for r in results
                 if r.criterion.predicate_type != "FREE_TEXT"]
    blockers = [r for r in evaluable if r.verdict is Verdict.NOT_MET]
    pending = [r for r in evaluable if r.verdict is Verdict.PENDING]
    unknown = [r for r in evaluable if r.verdict is Verdict.UNDETERMINED]

    missing = tuple(sorted({m for r in unknown for m in r.missing}))

    # A trial whose criteria are entirely free text was never actually checked.
    # Calling it ELIGIBLE_NOW would be the system's most dishonest possible
    # output: a green result for a patient it knows nothing about.
    if not evaluable:
        return TrialAssessment(
            trial_id, TrialState.UNDETERMINED, results,
            blocking_reason="no machine-checkable criteria; needs manual review",
        )

    if blockers:
        # Report an immutable blocker in preference to a correctable one: it is
        # the reason the trial can never open, not merely why it is shut today.
        hard = [r for r in blockers
                if r.criterion.mutability is Mutability.IMMUTABLE]
        lead = (hard or blockers)[0]
        return TrialAssessment(
            trial_id, TrialState.BLOCKED, results,
            blocking_reason=lead.reason, blocking_result=lead,
            missing_fields=missing,
        )

    if unknown:
        return TrialAssessment(
            trial_id, TrialState.UNDETERMINED, results,
            blocking_reason=f"{len(unknown)} criteria need data",
            missing_fields=missing,
        )

    if pending:
        # The latest window governs: the patient is not eligible until every
        # washout has closed.
        lead = max(pending, key=lambda r: r.eligible_date)
        return TrialAssessment(
            trial_id, TrialState.ELIGIBLE_ON_DATE, results,
            eligible_date=lead.eligible_date,
            blocking_reason=lead.reason, blocking_result=lead,
        )

    return TrialAssessment(trial_id, TrialState.ELIGIBLE_NOW, results)


def assess_all(compiled_by_trial, patient):
    """{trial_id: [Criterion]} -> [TrialAssessment], best states first."""
    out = [assess_trial(tid, cs, patient)
           for tid, cs in compiled_by_trial.items()]
    rank = {TrialState.ELIGIBLE_NOW: 0, TrialState.ELIGIBLE_ON_DATE: 1,
            TrialState.UNDETERMINED: 2, TrialState.BLOCKED: 3}
    out.sort(key=lambda a: (rank[a.state],
                            a.eligible_date or date.max,
                            len(a.missing_fields)))
    return out


def missing_data_panel(assessments, top=None):
    """Which tests to order, ranked by how many criteria and trials they unblock.

    Section 7 of the build spec: "order these four tests to resolve nine
    criteria across six trials."
    """
    crit_count, trial_count = Counter(), {}
    for a in assessments:
        for r in a.results:
            if r.verdict is not Verdict.UNDETERMINED:
                continue
            for m in r.missing:
                crit_count[m] += 1
                trial_count.setdefault(m, set()).add(a.trial_id)

    rows = [
        {"field": f, "criteria": n, "trials": len(trial_count[f]),
         "trial_ids": sorted(trial_count[f])}
        for f, n in crit_count.items()
    ]
    rows.sort(key=lambda x: (-x["trials"], -x["criteria"], x["field"]))
    return rows[:top] if top else rows


def missing_data_headline(rows):
    """"Order N tests to resolve C criteria across T trials."

    T is the UNION of trials the chosen tests unblock, not the largest single
    row -- the same trial usually needs several of them, so summing or taking a
    max both overstate the reach.
    """
    if not rows:
        return None
    union = set()
    for r in rows:
        union.update(r["trial_ids"])
    return {
        "tests": len(rows),
        "criteria": sum(r["criteria"] for r in rows),
        "trials": len(union),
    }


def eligibility_calendar(assessments):
    """Dates on which trials open, for the timeline view (stage 6)."""
    by_date = {}
    for a in assessments:
        if a.state is TrialState.ELIGIBLE_ON_DATE and a.eligible_date:
            by_date.setdefault(a.eligible_date, []).append(a)
    return [
        {"date": d, "trials": [x.trial_id for x in v],
         "reasons": [x.blocking_reason for x in v]}
        for d, v in sorted(by_date.items())
    ]
