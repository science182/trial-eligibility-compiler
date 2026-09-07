"""COMORBIDITY compiler tests, written against text from the corpus."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from compile import compile_comorbidities as C  # noqa: E402


def conds(r):
    return {p["condition"] for p in r}


def one(text, **kw):
    r = C(text, **kw)
    assert len(r) == 1, f"expected 1 payload, got {len(r)}: {r}"
    return r[0]


class TestNamedConditions:
    @pytest.mark.parametrize("text,cond", [
        ("Active brain metastases", "BRAIN_METASTASES"),
        ("Presence of leptomeningeal disease", "LEPTOMENINGEAL_DISEASE"),
        ("NYHA Class III or IV congestive heart failure.", "HEART_FAILURE"),
        ("Active tuberculosis", "TUBERCULOSIS"),
        ("Inflammatory bowel disease", "INFLAMMATORY_BOWEL_DISEASE"),
        ("Severe hepatic disease (Child-Pugh classification C)", "CIRRHOSIS"),
        ("Renal failure requiring renal replacement therapy", "RENAL_IMPAIRMENT"),
        ("Presence of primary immunodeficiency diseases.", "IMMUNODEFICIENCY"),
        ("Uncontrolled ascites.", "ASCITES"),
        ("History of retinal vein occlusion (RVO)", "OCULAR_DISORDER"),
    ])
    def test_condition_is_identified(self, text, cond):
        assert cond in conds(C(text))

    def test_several_conditions_in_one_criterion(self):
        r = C("Patients with interstitial pneumonia, pulmonary fibrosis, "
              "or severe emphysema;")
        assert {"INTERSTITIAL_LUNG_DISEASE", "COPD"} <= conds(r)

    def test_inline_abbreviation_does_not_split_the_phrase(self):
        # "central nervous system (CNS) metastases" is the registry's house
        # style and breaks a naive phrase match.
        assert "BRAIN_METASTASES" in conds(
            C("Active central nervous system (CNS) metastases"))

    def test_reversed_word_order(self):
        assert "BRAIN_METASTASES" in conds(
            C("Presence of metastases to brain stem, meninges and spinal cord"))


class TestQualifiers:
    @pytest.mark.parametrize("text,qual", [
        ("Active brain metastases", "active"),
        ("Uncontrolled hypertension", "uncontrolled"),
        ("Persistently symptomatic bone metastases.", "symptomatic"),
        ("History of pneumonitis in the past 5 years.", "history_of"),
        ("Severe hepatic disease", "severe"),
    ])
    def test_qualifier_captured(self, text, qual):
        assert one(text)["qualifier"] == qual

    def test_qualifier_does_not_cross_a_clause_boundary(self):
        # "active" belongs to the infection, not to the brain metastases.
        r = C("Active infection requiring treatment; stable brain metastases "
              "are eligible")
        by = {p["condition"]: p["qualifier"] for p in r}
        assert by["BRAIN_METASTASES"] != "active"


class TestExcludedDerivation:
    def test_exclusion_section_default(self):
        assert one("Active brain metastases", is_inclusion=False)["excluded"] is True

    def test_permitted_language_flips_it(self):
        r = C("Patients with asymptomatic central nervous system (CNS) "
              "metastases are allowed.", is_inclusion=True)
        assert r and all(p["excluded"] is False for p in r)

    def test_splitter_flip_is_not_double_negated(self):
        # The splitter already made this an exclusion. Reading "must not have"
        # again would cancel out and mark the condition as permitted.
        p = one("Participants must not have any history of primary "
                "immunodeficiency", is_inclusion=False, polarity_flipped=True)
        assert p["excluded"] is True

    def test_negated_inclusion_excludes(self):
        p = one("Patients with no history of interstitial lung disease",
                is_inclusion=True)
        assert p["excluded"] is True


class TestRejections:
    """An unnamed condition states a real restriction but nothing checkable."""

    @pytest.mark.parametrize("text", [
        "The presence of any other concurrent severe and/or uncontrolled "
        "medical condition that would contraindicate participation",
        "Any other significant physical and medical co-morbid conditions",
        "Other conditions assessed by the investigator to be unsuitable",
    ])
    def test_unnamed_catch_alls_stay_free_text(self, text):
        assert C(text) == []

    @pytest.mark.parametrize("text", [
        "Known hypersensitivity to atezolizumab or pirfenidone",
        "Known allergy to the active ingredient or excipients of the study drug",
    ])
    def test_hypersensitivity_is_not_a_comorbidity(self, text):
        assert C(text) == []

    def test_pregnancy_is_not_a_comorbidity(self):
        assert C("Women who are pregnant or breastfeeding.") == []

    def test_measurable_disease_is_not_a_comorbidity(self):
        assert C("At least one measurable disease lesion per RECIST v1.1") == []


class TestCarveOuts:
    def test_trailing_exception_does_not_void_the_criterion(self):
        # "except adequately treated basal cell carcinoma" trails the real
        # requirement; suppressing the whole sentence loses it.
        r = C("Diagnosis of any secondary malignancy within the last 3 years "
              "except for: adequately treated basal cell or squamous cell "
              "skin cancer, carcinoma in situ of the cervix")
        assert "SECOND_MALIGNANCY" in conds(r)

    def test_first_mention_wins_on_duplicates(self):
        r = C("History of other malignancies within 5 years, except "
              "malignant tumors expected to recover after treatment")
        assert len([p for p in r if p["condition"] == "SECOND_MALIGNANCY"]) == 1
