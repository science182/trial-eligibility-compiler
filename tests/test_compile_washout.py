"""WASHOUT compiler tests, written against text taken from the corpus."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from compile import compile_washouts as W  # noqa: E402


def classes(r):
    return {p["drug_or_class"] for p in r}


def one(text, context=()):
    r = W(text, context)
    assert len(r) == 1, f"expected 1 predicate, got {len(r)}: {r}"
    return r[0]


class TestBasicWindows:
    def test_within_weeks_prior_to_first_dose(self):
        p = one("Major surgery within 4 weeks of the first dose of study drug")
        assert p["drug_or_class"] == "SURGERY"
        assert (p["amount"], p["unit"]) == (4, "weeks")
        assert p["days"] == 28
        assert p["anchor_event"] == "first_dose"

    def test_within_days_prior_to_randomization(self):
        p = one("Live, attenuated vaccine within 28 days prior to randomization")
        assert p["drug_or_class"] == "LIVE_VACCINE"
        assert p["anchor_event"] == "randomization"

    def test_within_the_last_n_years(self):
        # "within the last" defeats a \bin the last\b pattern.
        p = one("Diagnosis of any secondary malignancy within the last 3 years")
        # conditions.py and drugs.py used two names for one concept;
        # unified on SECOND_MALIGNANCY.
        assert p["drug_or_class"] == "SECOND_MALIGNANCY"
        assert (p["amount"], p["unit"]) == (3, "years")

    def test_marker_after_the_duration(self):
        # "surgery 4-12 weeks prior to enrollment" has no marker in front.
        p = one("Completed radical surgery for lung cancer 4-12 weeks "
                "prior to study enrollment")
        assert p["drug_or_class"] == "SURGERY"
        assert p["anchor_event"] == "enrollment"

    def test_range_takes_the_binding_edge(self):
        # 4-12 weeks: ineligible until the wider window closes.
        p = one("Completed radical surgery for lung cancer 4-12 weeks "
                "prior to study enrollment")
        assert p["amount"] == 12

    def test_worded_number(self):
        p = one("Corticosteroid doses stable for at least one month before inclusion")
        assert (p["amount"], p["unit"]) == (1, "months")


class TestMultipleSubjects:
    def test_or_joined_subjects_share_the_window(self):
        r = W("Receipt of systemic corticosteroids or other immunosuppressive "
              "therapy within 2 weeks prior to the first dose of study drug")
        assert classes(r) == {"CORTICOSTEROIDS", "IMMUNOSUPPRESSANTS"}
        assert all(p["days"] == 14 for p in r)

    def test_list_of_modalities_shares_the_window(self):
        r = W("Anti-cancer therapy including chemotherapy, radiation therapy, "
              "immunotherapy within 28 days of first dose")
        assert {"CHEMOTHERAPY", "RADIOTHERAPY", "IMMUNOTHERAPY"} <= classes(r)

    def test_window_stated_before_its_subject(self):
        r = W(">= 6 months interval between recurrence and discontinuation "
              "of adjuvant osimertinib")
        assert r and r[0]["amount"] == 6


class TestHalfLives:
    def test_day_count_kept_and_half_life_flagged(self):
        p = one("Monoclonal antibodies: >= 5 half-lives or >= 42 days, "
                "whichever is longer.")
        assert p["drug_or_class"] == "MONOCLONAL_ANTIBODY"
        assert p["days"] == 42
        assert p["half_lives"] == 5
        assert p["whichever"] == "longer"

    def test_half_lives_alone_are_not_computable(self):
        # No day count means no date can be produced; must not compile.
        assert W("Investigational agents within 5 half-lives of the compound") == []


class TestContextInheritance:
    HDR = ("Any of the following within 6 months before the first dose "
           "of study treatment:",)

    def test_child_inherits_the_parent_window(self):
        p = one("unstable angina pectoris", self.HDR)
        assert p["drug_or_class"] == "ANGINA"
        assert (p["amount"], p["unit"]) == (6, "months")
        assert p["window_from_context"] is True

    def test_all_subjects_in_the_child_are_bound(self):
        r = W("stroke (including TIA, or other ischemic event) myocardial infarction",
              self.HDR)
        assert classes(r) == {"STROKE", "MYOCARDIAL_INFARCTION"}

    def test_own_window_beats_inherited(self):
        p = one("Major surgery within 4 weeks of the first dose", self.HDR)
        assert p["amount"] == 4
        assert p["window_from_context"] is False

    def test_no_subject_means_no_predicate(self):
        assert W("The subject is able to swallow tablets", self.HDR) == []


class TestRejections:
    """A window we cannot attach to a date lookup must not become a predicate."""

    def test_lab_recency_window_is_not_a_washout(self):
        assert W(r"Hemoglobin \> 9.0 g/dL (within 28 days prior to randomization)") == []
        assert W("Absolute neutrophil count >= 1.5 x 10^3/uL "
                 "(within 28 days prior to randomization)") == []

    @pytest.mark.parametrize("text", [
        "Life expectancy of at least 12 weeks.",
        "Estimated life expectancy of at least 3 months",
        "Projected life expectancy >= 12 weeks in the opinion of the Investigator.",
    ])
    def test_life_expectancy_is_not_a_washout(self, text):
        assert W(text) == []

    def test_age_is_not_a_washout(self):
        assert W("At least 18 years and no older than 85 years at signing of the ICF") == []
        assert W("Subjects aged >= 18 and <= 75 years at enrollment") == []

    def test_postmenopausal_definition_is_not_a_washout(self):
        assert W("Postmenopause is defined as amenorrhea >= 12 consecutive months") == []
        assert W("cessation of regular menses for at least 12 consecutive months") == []

    def test_forward_looking_contraception_window_is_not_a_washout(self):
        assert W("Male patients should use barrier contraception for 6 months "
                 "after the last dose") == []

    def test_no_duration_no_predicate(self):
        assert W("Prior treatment with cabozantinib") == []

    def test_no_recognised_subject_no_predicate(self):
        assert W("Patients who participated in other activities within the last 1 month") == []


class TestPayloadShape:
    def test_exact_flag_marks_calendar_units(self):
        assert one("Major surgery within 4 weeks of the first dose")["exact"] is True
        p = one("Diagnosis of any secondary malignancy within the last 3 years")
        assert p["exact"] is False, "months/years need calendar arithmetic"

    def test_inferred_anchor_is_flagged(self):
        p = one("Diagnosis of any secondary malignancy within the last 3 years")
        assert p["anchor_inferred"] is True

    def test_stated_anchor_is_not_flagged(self):
        p = one("Live, attenuated vaccine within 28 days prior to randomization")
        assert p["anchor_inferred"] is False
