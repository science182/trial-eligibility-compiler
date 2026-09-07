"""Evaluation engine tests.

Section 10 requires MET / NOT_MET / UNDETERMINED / PENDING for every predicate
type, plus boundary tests where a value sits exactly on the threshold.
"""

import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from compile import Criterion, Mutability  # noqa: E402
from evaluate import Verdict, evaluate_criterion, evaluate_predicate  # noqa: E402
from patient import (Biomarker, LabValue, PatientRecord,  # noqa: E402
                     PriorTherapy, Sourced)

TODAY = date(2026, 8, 14)


def crit(ptype, payload, is_inclusion=True, mut=Mutability.UNKNOWN):
    return Criterion(trial_id="NCT0", raw_text="test", is_inclusion=is_inclusion,
                     predicate_type=ptype, mutability=mut, payload=payload,
                     compiled=True)


def patient(**kw):
    return PatientRecord(index_date=TODAY, **kw)


def v(c, p):
    return evaluate_predicate(c, p).verdict


# =============================================================== LAB

class TestLabThreshold:
    def lab_c(self, **over):
        p = {"analyte": "ANC", "operator": ">=", "value": 1.5, "unit": "10^9/L",
             "basis": "absolute", "condition": None, "group": 0}
        p.update(over)
        return crit("LAB_THRESHOLD", p, mut=Mutability.CORRECTABLE)

    def with_anc(self, val, **kw):
        return patient(labs={"ANC": LabValue("ANC", val, "10^9/L", **kw)})

    def test_met(self):
        assert v(self.lab_c(), self.with_anc(2.0)) is Verdict.MET

    def test_not_met(self):
        assert v(self.lab_c(), self.with_anc(1.0)) is Verdict.NOT_MET

    def test_undetermined_when_analyte_absent(self):
        r = evaluate_predicate(self.lab_c(), patient())
        assert r.verdict is Verdict.UNDETERMINED
        assert r.missing == ("lab:ANC",)

    # -- boundary: the most likely silent bug in the system -------------
    def test_boundary_equal_inclusive_ge(self):
        assert v(self.lab_c(operator=">="), self.with_anc(1.5)) is Verdict.MET

    def test_boundary_equal_exclusive_gt(self):
        assert v(self.lab_c(operator=">"), self.with_anc(1.5)) is Verdict.NOT_MET

    def test_boundary_equal_inclusive_le(self):
        c = self.lab_c(analyte="BILIRUBIN", operator="<=", value=1.5,
                       unit="mg/dL")
        p = patient(labs={"BILIRUBIN": LabValue("BILIRUBIN", 1.5, "mg/dL")})
        assert v(c, p) is Verdict.MET

    def test_boundary_equal_exclusive_lt(self):
        c = self.lab_c(analyte="BILIRUBIN", operator="<", value=1.5,
                       unit="mg/dL")
        p = patient(labs={"BILIRUBIN": LabValue("BILIRUBIN", 1.5, "mg/dL")})
        assert v(c, p) is Verdict.NOT_MET

    def test_just_below_and_just_above(self):
        assert v(self.lab_c(), self.with_anc(1.4999)) is Verdict.NOT_MET
        assert v(self.lab_c(), self.with_anc(1.5001)) is Verdict.MET


class TestUlnRelativeThresholds:
    def bili(self, mult=1.5):
        return crit("LAB_THRESHOLD",
                    {"analyte": "BILIRUBIN", "operator": "<=", "value": mult,
                     "unit": "ULN", "basis": "uln", "condition": None,
                     "group": 0})

    def test_uses_institutional_limit_when_reported(self):
        p = patient(labs={"BILIRUBIN": LabValue("BILIRUBIN", 1.4, "mg/dL",
                                                uln=1.0)})
        # 1.5 x 1.0 = 1.5, patient 1.4 -> MET
        assert v(self.bili(), p) is Verdict.MET

    def test_institutional_limit_changes_the_verdict(self):
        p = patient(labs={"BILIRUBIN": LabValue("BILIRUBIN", 1.4, "mg/dL",
                                                uln=0.8)})
        # 1.5 x 0.8 = 1.2, patient 1.4 -> NOT_MET
        assert v(self.bili(), p) is Verdict.NOT_MET

    def test_falls_back_to_default_and_flags_it(self):
        p = patient(labs={"BILIRUBIN": LabValue("BILIRUBIN", 1.4, "mg/dL")})
        r = evaluate_predicate(self.bili(), p)
        assert r.verdict is Verdict.MET          # 1.5 x 1.2 = 1.8
        assert r.assumed == ("default reference limit",)


class TestConditionalVariants:
    def ast(self, mult, cond):
        return crit("LAB_THRESHOLD",
                    {"analyte": "AST", "operator": "<=", "value": mult,
                     "unit": "ULN", "basis": "uln", "condition": cond,
                     "group": 0})

    def test_liver_variant_selected_when_condition_holds(self):
        p = patient(labs={"AST": LabValue("AST", 150, "U/L")},
                    comorbidities=[Sourced("LIVER_METASTASES")])
        # base 2.5x40=100 fails; liver variant 5x40=200 passes; OR'd -> MET
        base, var = self.ast(2.5, None), self.ast(5.0, "liver_metastases")
        assert evaluate_criterion([base, var], p).verdict is Verdict.MET

    def test_liver_variant_ignored_when_condition_absent(self):
        p = patient(labs={"AST": LabValue("AST", 150, "U/L")},
                    negative_findings={"LIVER_METASTASES"})
        base, var = self.ast(2.5, None), self.ast(5.0, "liver_metastases")
        assert evaluate_criterion([base, var], p).verdict is Verdict.NOT_MET

    def test_unknown_condition_is_undetermined(self):
        p = patient(labs={"AST": LabValue("AST", 150, "U/L")})
        assert v(self.ast(5.0, "liver_metastases"), p) is Verdict.UNDETERMINED


class TestDisjunctionGroups:
    def test_either_route_satisfies(self):
        cr = crit("LAB_THRESHOLD",
                  {"analyte": "CREATININE", "operator": "<=", "value": 1.5,
                   "unit": "ULN", "basis": "uln", "condition": None, "group": 0})
        crcl = crit("LAB_THRESHOLD",
                    {"analyte": "CREATININE_CLEARANCE", "operator": ">=",
                     "value": 40, "unit": "mL/min", "basis": "absolute",
                     "condition": None, "group": 0})
        p = patient(labs={
            "CREATININE": LabValue("CREATININE", 2.0, "mg/dL"),      # fails
            "CREATININE_CLEARANCE": LabValue("CREATININE_CLEARANCE", 55,
                                             "mL/min"),              # passes
        })
        assert evaluate_criterion([cr, crcl], p).verdict is Verdict.MET

    def test_separate_groups_are_both_required(self):
        a = crit("LAB_THRESHOLD",
                 {"analyte": "ANC", "operator": ">=", "value": 1.5,
                  "unit": "10^9/L", "basis": "absolute", "condition": None,
                  "group": 0})
        b = crit("LAB_THRESHOLD",
                 {"analyte": "PLATELETS", "operator": ">=", "value": 100,
                  "unit": "10^9/L", "basis": "absolute", "condition": None,
                  "group": 1})
        p = patient(labs={"ANC": LabValue("ANC", 2.0, "10^9/L"),
                          "PLATELETS": LabValue("PLATELETS", 80, "10^9/L")})
        assert evaluate_criterion([a, b], p).verdict is Verdict.NOT_MET


# =========================================================== WASHOUT

class TestWashout:
    def wc(self, amount=4, unit="weeks", cls="CHEMOTHERAPY"):
        return crit("WASHOUT",
                    {"drug_or_class": cls, "subject_kind": "therapy",
                     "days": amount * 7, "amount": amount, "unit": unit,
                     "exact": True, "anchor_event": "first_dose",
                     "anchor_inferred": False, "half_lives": None,
                     "whichever": None, "window_from_context": False},
                    is_inclusion=False, mut=Mutability.TEMPORAL)

    def test_met_when_window_has_elapsed(self):
        p = patient(last_dose_dates={"CHEMOTHERAPY": date(2026, 6, 1)})
        assert v(self.wc(), p) is Verdict.MET

    def test_pending_with_a_computed_date(self):
        p = patient(last_dose_dates={"CHEMOTHERAPY": date(2026, 8, 1)})
        r = evaluate_predicate(self.wc(), p)
        assert r.verdict is Verdict.PENDING
        assert r.eligible_date == date(2026, 8, 29)     # 1 Aug + 4 weeks
        assert r.anchor_date == date(2026, 8, 1)

    def test_undetermined_without_an_anchor_date(self):
        # Never guess an anchor: no date means no eligibility date.
        r = evaluate_predicate(self.wc(), patient())
        assert r.verdict is Verdict.UNDETERMINED
        assert r.eligible_date is None
        assert r.missing == ("date:CHEMOTHERAPY",)

    def test_boundary_exactly_on_the_window_end(self):
        # 17 July + 4 weeks = 14 Aug = today -> the washout has elapsed.
        p = patient(last_dose_dates={"CHEMOTHERAPY": date(2026, 7, 17)})
        assert v(self.wc(), p) is Verdict.MET

    def test_boundary_one_day_short(self):
        p = patient(last_dose_dates={"CHEMOTHERAPY": date(2026, 7, 18)})
        r = evaluate_predicate(self.wc(), p)
        assert r.verdict is Verdict.PENDING
        assert r.eligible_date == date(2026, 8, 15)

    def test_calendar_months_not_thirty_days(self):
        # 28 Feb + 6 calendar months = 28 Aug. A 180-day approximation gives
        # 27 Aug -- a day earlier, and on the wrong side of a clinic visit.
        from datetime import timedelta
        c = self.wc(amount=6, unit="months")
        anchor = date(2026, 2, 28)
        r = evaluate_predicate(c, patient(last_dose_dates={"CHEMOTHERAPY": anchor}))
        assert r.verdict is Verdict.PENDING
        assert r.eligible_date == date(2026, 8, 28)
        assert r.eligible_date != anchor + timedelta(days=180)
        assert r.anchor_date == anchor

    def test_month_end_clamping_in_a_pending_date(self):
        c = self.wc(amount=1, unit="months")
        p = patient(last_dose_dates={"CHEMOTHERAPY": date(2026, 7, 31)})
        r = evaluate_predicate(c, p)
        assert r.verdict is Verdict.PENDING
        assert r.eligible_date == date(2026, 8, 31)

    def test_event_dates_are_also_valid_anchors(self):
        c = self.wc(amount=3, unit="years", cls="PRIOR_MALIGNANCY")
        p = patient(event_dates={"PRIOR_MALIGNANCY": date(2025, 1, 1)})
        r = evaluate_predicate(c, p)
        assert r.verdict is Verdict.PENDING
        assert r.eligible_date == date(2028, 1, 1)


# =============================================================== AGE

class TestAge:
    def ac(self, lo=18, hi=None):
        return crit("AGE", {"min_years": lo, "max_years": hi},
                    mut=Mutability.IMMUTABLE)

    def test_met(self):
        assert v(self.ac(), patient(age=Sourced(64))) is Verdict.MET

    def test_not_met_below_minimum(self):
        assert v(self.ac(), patient(age=Sourced(17))) is Verdict.NOT_MET

    def test_not_met_above_maximum(self):
        assert v(self.ac(18, 75), patient(age=Sourced(80))) is Verdict.NOT_MET

    def test_undetermined(self):
        assert v(self.ac(), patient()) is Verdict.UNDETERMINED

    def test_boundaries_are_inclusive(self):
        assert v(self.ac(18, 75), patient(age=Sourced(18))) is Verdict.MET
        assert v(self.ac(18, 75), patient(age=Sourced(75))) is Verdict.MET


# ================================================ PERFORMANCE_STATUS

class TestPerformanceStatus:
    def ps(self, **over):
        p = {"scale": "ECOG", "min_value": 0, "max_value": 1,
             "operator": None, "value": None}
        p.update(over)
        return crit("PERFORMANCE_STATUS", p, mut=Mutability.CORRECTABLE)

    def test_met(self):
        assert v(self.ps(), patient(ecog=Sourced(1))) is Verdict.MET

    def test_not_met(self):
        assert v(self.ps(), patient(ecog=Sourced(2))) is Verdict.NOT_MET

    def test_undetermined(self):
        assert v(self.ps(), patient()) is Verdict.UNDETERMINED

    def test_boundary_at_max(self):
        assert v(self.ps(max_value=2), patient(ecog=Sourced(2))) is Verdict.MET

    def test_operator_form_is_not_inverted(self):
        # An exclusion "ECOG > 1": a patient at 2 satisfies the predicate.
        c = self.ps(min_value=None, max_value=None, operator=">", value=1)
        assert v(c, patient(ecog=Sourced(2))) is Verdict.MET
        assert v(c, patient(ecog=Sourced(1))) is Verdict.NOT_MET

    def test_karnofsky_needs_a_karnofsky_score(self):
        c = self.ps(scale="KARNOFSKY", min_value=70, max_value=None)
        assert v(c, patient(ecog=Sourced(0))) is Verdict.UNDETERMINED
        assert v(c, patient(karnofsky=Sourced(90))) is Verdict.MET


# ========================================================= HISTOLOGY

class TestHistology:
    def hc(self, allowed=("NSCLC",), excluded=()):
        return crit("HISTOLOGY",
                    {"allowed_codes": list(allowed),
                     "excluded_codes": list(excluded)},
                    mut=Mutability.IMMUTABLE)

    def test_exact_match(self):
        assert v(self.hc(), patient(histology=Sourced("NSCLC"))) is Verdict.MET

    def test_subtype_satisfies_parent(self):
        p = patient(histology=Sourced("ADENOCARCINOMA"))
        assert v(self.hc(("NSCLC",)), p) is Verdict.MET
        assert v(self.hc(("NSCLC_NONSQUAMOUS",)), p) is Verdict.MET

    def test_wrong_subtype(self):
        p = patient(histology=Sourced("NSCLC_SQUAMOUS"))
        assert v(self.hc(("NSCLC_NONSQUAMOUS",)), p) is Verdict.NOT_MET

    def test_excluded_histology(self):
        p = patient(histology=Sourced("SCLC"))
        assert v(self.hc((), ("SCLC",)), p) is Verdict.NOT_MET

    def test_undetermined(self):
        assert v(self.hc(), patient()) is Verdict.UNDETERMINED


# ============================================================= STAGE

class TestStage:
    def sc(self, stages):
        return crit("STAGE", {"allowed_stages": list(stages),
                              "from_descriptor": False},
                    mut=Mutability.IMMUTABLE)

    def test_met(self):
        assert v(self.sc(["IV"]), patient(stage=Sourced("IV"))) is Verdict.MET

    def test_not_met(self):
        assert v(self.sc(["IV"]), patient(stage=Sourced("IIIA"))) is Verdict.NOT_MET

    def test_expanded_range_includes_substage(self):
        c = self.sc(["II", "IIA", "IIB", "III", "IIIA", "IIIB"])
        assert v(c, patient(stage=Sourced("IIIA"))) is Verdict.MET

    def test_undetermined(self):
        assert v(self.sc(["IV"]), patient()) is Verdict.UNDETERMINED


# ========================================================= BIOMARKER

class TestBiomarker:
    def bc(self, gene="EGFR", alt="MUTATION", required=True):
        return crit("BIOMARKER",
                    {"gene": gene, "alteration": alt, "required": required},
                    mut=Mutability.IMMUTABLE)

    def test_required_and_present(self):
        p = patient(biomarkers=[Biomarker("EGFR", "L858R")])
        assert v(self.bc(), p) is Verdict.MET

    def test_required_and_absent(self):
        p = patient(biomarkers=[Biomarker("KRAS", "G12C")])
        p.genes_tested = {"EGFR"}
        assert v(self.bc(), p) is Verdict.NOT_MET

    def test_must_be_absent_and_present(self):
        p = patient(biomarkers=[Biomarker("EGFR", "L858R")])
        assert v(self.bc(required=False), p) is Verdict.NOT_MET

    def test_must_be_absent_and_absent(self):
        p = patient(biomarkers=[])
        p.genes_tested = {"EGFR"}
        assert v(self.bc(required=False), p) is Verdict.MET

    def test_untested_gene_is_undetermined_not_absent(self):
        # The key distinction: "not tested" must never read as "negative".
        assert v(self.bc(), patient()) is Verdict.UNDETERMINED

    def test_specific_alteration_must_match(self):
        p = patient(biomarkers=[Biomarker("EGFR", "L858R")])
        assert v(self.bc(alt="T790M"), p) is Verdict.NOT_MET
        assert v(self.bc(alt="L858R"), p) is Verdict.MET


# ==================================================== PRIOR_THERAPY

class TestPriorTherapy:
    def pc(self, **over):
        p = {"drug_class": "CHECKPOINT_INHIBITOR", "min_lines": None,
             "max_lines": None, "exact_lines": None, "count_unit": None,
             "required": True, "setting": None, "progressed_on": False}
        p.update(over)
        return crit("PRIOR_THERAPY", p, mut=Mutability.IMMUTABLE)

    def complete(self, therapies):
        p = patient(prior_therapies=therapies)
        p.therapy_history_complete = True
        return p

    def test_required_and_present(self):
        p = patient(prior_therapies=[
            PriorTherapy(drug_class="CHECKPOINT_INHIBITOR", line=1)])
        assert v(self.pc(), p) is Verdict.MET

    def test_required_and_absent_from_a_complete_history(self):
        p = self.complete([PriorTherapy(drug_class="CHEMOTHERAPY")])
        assert v(self.pc(), p) is Verdict.NOT_MET

    def test_absent_from_an_incomplete_history_is_undetermined(self):
        # A note listing two systemic therapies does not assert the patient
        # never had surgery. Silence is not absence.
        p = patient(prior_therapies=[PriorTherapy(drug_class="CHEMOTHERAPY")])
        r = evaluate_predicate(self.pc(drug_class="SURGERY"), p)
        assert r.verdict is Verdict.UNDETERMINED
        assert r.missing == ("therapy:SURGERY",)

    def test_explicitly_ruled_out_class_is_absent(self):
        p = patient(prior_therapies=[PriorTherapy(drug_class="CHEMOTHERAPY")],
                    negative_findings={"CHECKPOINT_INHIBITOR"})
        assert v(self.pc(), p) is Verdict.NOT_MET

    def test_must_not_have_had_it(self):
        p = patient(prior_therapies=[
            PriorTherapy(drug_class="CHECKPOINT_INHIBITOR")])
        assert v(self.pc(required=False), p) is Verdict.NOT_MET

    def test_undetermined_without_a_history(self):
        assert v(self.pc(), patient()) is Verdict.UNDETERMINED

    def test_line_cap_met(self):
        p = self.complete([
            PriorTherapy(drug_class="CHEMOTHERAPY", line=1),
            PriorTherapy(drug_class="CHECKPOINT_INHIBITOR", line=2)])
        assert v(self.pc(drug_class="ANY", max_lines=3), p) is Verdict.MET

    def test_line_cap_exceeded(self):
        p = self.complete([
            PriorTherapy(drug_class="CHEMOTHERAPY", line=i) for i in (1, 2, 3, 4)])
        assert v(self.pc(drug_class="ANY", max_lines=3), p) is Verdict.NOT_MET

    def test_line_cap_boundary_is_inclusive(self):
        p = self.complete([
            PriorTherapy(drug_class="CHEMOTHERAPY", line=i) for i in (1, 2, 3)])
        assert v(self.pc(drug_class="ANY", max_lines=3), p) is Verdict.MET

    def test_lines_need_a_complete_history(self):
        p = patient(prior_therapies=[
            PriorTherapy(drug_class="CHEMOTHERAPY", line=1)])
        assert v(self.pc(drug_class="ANY", max_lines=3), p) \
            is Verdict.UNDETERMINED

    def test_cycles_are_not_countable_from_the_record(self):
        p = self.complete([PriorTherapy(drug_class="IMMUNOTHERAPY", line=1)])
        c = self.pc(drug_class="IMMUNOTHERAPY", min_lines=3, max_lines=4,
                    count_unit="cycles")
        assert v(c, p) is Verdict.UNDETERMINED

    def test_progression_requirement_undetermined_when_unrecorded(self):
        p = patient(prior_therapies=[
            PriorTherapy(drug_class="CHECKPOINT_INHIBITOR")])
        assert v(self.pc(progressed_on=True), p) is Verdict.UNDETERMINED

    def test_progression_requirement_met(self):
        p = patient(prior_therapies=[
            PriorTherapy(drug_class="CHECKPOINT_INHIBITOR", progressed=True)])
        assert v(self.pc(progressed_on=True), p) is Verdict.MET


# ======================================================= COMORBIDITY

class TestComorbidity:
    def cc(self, cond="BRAIN_METASTASES", excluded=True, qual="active"):
        return crit("COMORBIDITY",
                    {"condition": cond, "qualifier": qual, "excluded": excluded},
                    is_inclusion=False, mut=Mutability.UNKNOWN)

    def test_present_and_excluded(self):
        p = patient(comorbidities=[Sourced("BRAIN_METASTASES")])
        assert v(self.cc(), p) is Verdict.NOT_MET

    def test_documented_absent(self):
        p = patient(negative_findings={"BRAIN_METASTASES"})
        assert v(self.cc(), p) is Verdict.MET

    def test_silence_is_undetermined_not_absence(self):
        # The core reason COMORBIDITY resolves to UNDETERMINED so often:
        # reports rarely enumerate what the patient does NOT have.
        r = evaluate_predicate(self.cc(), patient())
        assert r.verdict is Verdict.UNDETERMINED
        assert r.missing == ("comorbidity:BRAIN_METASTASES",)

    def test_permitted_condition_is_met_even_when_present(self):
        p = patient(comorbidities=[Sourced("BRAIN_METASTASES")])
        assert v(self.cc(excluded=False), p) is Verdict.MET


# ======================================================== robustness

class TestRobustness:
    def test_malformed_payload_abstains(self):
        c = crit("LAB_THRESHOLD", {"analyte": "ANC"})     # missing keys
        p = patient(labs={"ANC": LabValue("ANC", 2.0, "10^9/L")})
        assert evaluate_predicate(c, p).verdict is Verdict.UNDETERMINED

    def test_unknown_type_abstains(self):
        assert evaluate_predicate(crit("FREE_TEXT", {}), patient()).verdict \
            is Verdict.UNDETERMINED

    def test_worst_verdict_wins_across_groups(self):
        met = crit("AGE", {"min_years": 18, "max_years": None}, )
        bad = crit("STAGE", {"allowed_stages": ["IV"], "from_descriptor": False})
        p = patient(age=Sourced(70), stage=Sourced("I"))
        assert evaluate_criterion([met, bad], p).verdict is Verdict.NOT_MET


class TestExclusionPolarity:
    """MET means the patient SATISFIES the criterion, whichever section it is in.

    Found by metric 9.2: every exclusion criterion of these types was being
    evaluated backwards, so a patient with a normal QTc was blocked and one
    with a prolonged QTc passed.
    """

    def excl(self, ptype, payload, mut=Mutability.CORRECTABLE):
        return crit(ptype, payload, is_inclusion=False, mut=mut)

    def test_lab_exclusion_not_triggered_is_met(self):
        c = self.excl("LAB_THRESHOLD",
                      {"analyte": "QTC", "operator": ">", "value": 470,
                       "unit": "ms", "basis": "absolute", "condition": None,
                       "group": 0})
        p = patient(labs={"QTC": LabValue("QTC", 450, "ms")})
        assert v(c, p) is Verdict.MET

    def test_lab_exclusion_triggered_is_not_met(self):
        c = self.excl("LAB_THRESHOLD",
                      {"analyte": "QTC", "operator": ">", "value": 470,
                       "unit": "ms", "basis": "absolute", "condition": None,
                       "group": 0})
        p = patient(labs={"QTC": LabValue("QTC", 500, "ms")})
        assert v(c, p) is Verdict.NOT_MET

    def test_prior_therapy_exclusion_polarity(self):
        c = self.excl("PRIOR_THERAPY",
                      {"drug_class": "EGFR_TKI", "min_lines": None,
                       "max_lines": None, "exact_lines": None,
                       "count_unit": None, "required": True, "setting": None,
                       "progressed_on": False}, Mutability.IMMUTABLE)
        had = patient(prior_therapies=[PriorTherapy(drug_class="EGFR_TKI")])
        had.therapy_history_complete = True
        assert v(c, had) is Verdict.NOT_MET
        never = patient(prior_therapies=[PriorTherapy(drug_class="CHEMOTHERAPY")])
        never.therapy_history_complete = True
        assert v(c, never) is Verdict.MET

    def test_uln_threshold_survives_float_rounding(self):
        # 1.5 * 1.2 == 1.7999999999999998, so a patient at exactly 1.8 would
        # fail a "<= 1.5 x ULN" bound without rounding.
        c = crit("LAB_THRESHOLD",
                 {"analyte": "CREATININE", "operator": "<=", "value": 1.5,
                  "unit": "ULN", "basis": "uln", "condition": None, "group": 0})
        p = patient(labs={"CREATININE": LabValue("CREATININE", 1.8, "mg/dL",
                                                 uln=1.2)})
        assert v(c, p) is Verdict.MET
