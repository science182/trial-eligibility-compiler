"""Aggregation to the four trial states."""

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from aggregate import (TrialState, assess_all, assess_trial,  # noqa: E402
                       eligibility_calendar, missing_data_panel)
from compile import Criterion, Mutability  # noqa: E402
from patient import LabValue, PatientRecord, Sourced  # noqa: E402

TODAY = date(2026, 8, 14)


def patient(**kw):
    return PatientRecord(index_date=TODAY, **kw)


def age_c(lo=18, start=0):
    return Criterion("NCT0", "Age >= 18 years", True, "AGE",
                     Mutability.IMMUTABLE, {"min_years": lo, "max_years": None},
                     True, start, start + 10)


def stage_c(stages, start=20):
    return Criterion("NCT0", "Stage IV NSCLC", True, "STAGE",
                     Mutability.IMMUTABLE,
                     {"allowed_stages": list(stages), "from_descriptor": False},
                     True, start, start + 10)


def anc_c(threshold=1.5, start=40):
    return Criterion("NCT0", "ANC >= 1.5", True, "LAB_THRESHOLD",
                     Mutability.CORRECTABLE,
                     {"analyte": "ANC", "operator": ">=", "value": threshold,
                      "unit": "10^9/L", "basis": "absolute", "condition": None,
                      "group": 0}, True, start, start + 10)


def washout_c(cls="CHEMOTHERAPY", amount=4, unit="weeks", start=60):
    return Criterion("NCT0", f"{cls} within {amount} {unit}", False, "WASHOUT",
                     Mutability.TEMPORAL,
                     {"drug_or_class": cls, "subject_kind": "therapy",
                      "days": amount * 7, "amount": amount, "unit": unit,
                      "exact": True, "anchor_event": "first_dose",
                      "anchor_inferred": False, "half_lives": None,
                      "whichever": None, "window_from_context": False},
                     True, start, start + 10)


FULL = dict(age=Sourced(64), stage=Sourced("IV"),
            labs={"ANC": LabValue("ANC", 2.0, "10^9/L")})


class TestFourStates:
    def test_eligible_now(self):
        a = assess_trial("NCT0", [age_c(), stage_c(["IV"]), anc_c()],
                         patient(**FULL))
        assert a.state is TrialState.ELIGIBLE_NOW
        assert a.eligible_date is None

    def test_blocked_by_an_immutable_criterion(self):
        a = assess_trial("NCT0", [age_c(), stage_c(["I", "II"])],
                         patient(**FULL))
        assert a.state is TrialState.BLOCKED
        # Reason text is prose for a coordinator, so assert on meaning rather
        # than on exact casing.
        assert a.blocking_reason.lower().startswith("stage iv")

    def test_undetermined_when_data_is_missing(self):
        a = assess_trial("NCT0", [age_c(), stage_c(["IV"]), anc_c()],
                         patient(age=Sourced(64), stage=Sourced("IV")))
        assert a.state is TrialState.UNDETERMINED
        assert a.missing_fields == ("lab:ANC",)

    def test_eligible_on_a_date(self):
        p = patient(**FULL, last_dose_dates={"CHEMOTHERAPY": date(2026, 8, 1)})
        a = assess_trial("NCT0", [age_c(), stage_c(["IV"]), anc_c(),
                                  washout_c()], p)
        assert a.state is TrialState.ELIGIBLE_ON_DATE
        assert a.eligible_date == date(2026, 8, 29)

    def test_latest_washout_governs(self):
        p = patient(**FULL, last_dose_dates={
            "CHEMOTHERAPY": date(2026, 8, 1),          # opens 29 Aug
            "RADIOTHERAPY": date(2026, 8, 10),         # opens 7 Sep
        })
        a = assess_trial("NCT0", [
            age_c(), washout_c("CHEMOTHERAPY", start=60),
            washout_c("RADIOTHERAPY", start=80)], p)
        assert a.eligible_date == date(2026, 9, 7)


class TestStatePrecedence:
    """A trial the patient can never enter must not be shown as 'waiting'."""

    def test_hard_block_outranks_a_pending_washout(self):
        p = patient(**FULL, last_dose_dates={"CHEMOTHERAPY": date(2026, 8, 1)})
        a = assess_trial("NCT0", [stage_c(["I"]), washout_c()], p)
        assert a.state is TrialState.BLOCKED

    def test_hard_block_outranks_missing_data(self):
        p = patient(age=Sourced(64), stage=Sourced("I"))
        a = assess_trial("NCT0", [stage_c(["IV"]), anc_c()], p)
        assert a.state is TrialState.BLOCKED

    def test_missing_data_outranks_a_pending_washout(self):
        p = patient(age=Sourced(64), stage=Sourced("IV"),
                    last_dose_dates={"CHEMOTHERAPY": date(2026, 8, 1)})
        a = assess_trial("NCT0", [anc_c(), washout_c()], p)
        assert a.state is TrialState.UNDETERMINED

    def test_immutable_blocker_is_reported_over_a_correctable_one(self):
        p = patient(age=Sourced(64), stage=Sourced("I"),
                    labs={"ANC": LabValue("ANC", 0.5, "10^9/L")})
        a = assess_trial("NCT0", [anc_c(), stage_c(["IV"])], p)
        assert a.state is TrialState.BLOCKED
        assert "stage" in a.blocking_reason.lower()


class TestRanking:
    def test_best_states_first(self):
        p = patient(**FULL, last_dose_dates={"CHEMOTHERAPY": date(2026, 8, 1)})
        trials = {
            "BLOCKED": [stage_c(["I"])],
            "NOW": [age_c()],
            "DATE": [washout_c()],
            "UNKNOWN": [anc_c(threshold=1.5, start=40)],
        }
        p2 = patient(age=Sourced(64), stage=Sourced("IV"),
                     last_dose_dates={"CHEMOTHERAPY": date(2026, 8, 1)})
        order = [a.trial_id for a in assess_all(trials, p2)]
        assert order.index("NOW") < order.index("DATE")
        assert order.index("DATE") < order.index("UNKNOWN")
        assert order.index("UNKNOWN") < order.index("BLOCKED")


class TestMissingDataPanel:
    def test_ranks_by_trials_unblocked(self):
        p = patient(age=Sourced(64), stage=Sourced("IV"))
        trials = {f"NCT{i}": [anc_c()] for i in range(3)}
        trials["NCT9"] = [Criterion("NCT9", "ECOG 0-1", True,
                                    "PERFORMANCE_STATUS", Mutability.CORRECTABLE,
                                    {"scale": "ECOG", "min_value": 0,
                                     "max_value": 1, "operator": None,
                                     "value": None}, True, 0, 5)]
        rows = missing_data_panel(assess_all(trials, p))
        assert rows[0]["field"] == "lab:ANC"
        assert rows[0]["trials"] == 3
        assert {r["field"] for r in rows} == {"lab:ANC", "ecog"}


class TestEligibilityCalendar:
    def test_groups_trials_by_opening_date(self):
        p = patient(**FULL, last_dose_dates={
            "CHEMOTHERAPY": date(2026, 8, 1), "RADIOTHERAPY": date(2026, 8, 10)})
        trials = {
            "A": [age_c(), washout_c("CHEMOTHERAPY")],
            "B": [age_c(), washout_c("CHEMOTHERAPY")],
            "C": [age_c(), washout_c("RADIOTHERAPY")],
        }
        cal = eligibility_calendar(assess_all(trials, p))
        assert [c["date"] for c in cal] == [date(2026, 8, 29), date(2026, 9, 7)]
        assert sorted(cal[0]["trials"]) == ["A", "B"]
        assert cal[1]["trials"] == ["C"]

    def test_only_dated_trials_appear(self):
        a = assess_all({"X": [age_c()]}, patient(**FULL))
        assert eligibility_calendar(a) == []


class TestUncheckableTrials:
    """A trial we never checked must not be shown as eligible."""

    def test_free_text_only_trial_is_undetermined(self):
        ft = Criterion("NCT0", "Willing to comply with study procedures", True,
                       "FREE_TEXT", Mutability.UNKNOWN, {}, False, 0, 10)
        a = assess_trial("NCT0", [ft], patient(**FULL))
        assert a.state is TrialState.UNDETERMINED
        assert "machine-checkable" in a.blocking_reason

    def test_a_trial_with_one_real_criterion_still_resolves(self):
        ft = Criterion("NCT0", "Willing to comply", True, "FREE_TEXT",
                       Mutability.UNKNOWN, {}, False, 0, 10)
        a = assess_trial("NCT0", [ft, age_c()], patient(**FULL))
        assert a.state is TrialState.ELIGIBLE_NOW
