"""PRIOR_THERAPY compiler tests, written against text from the corpus."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from compile import compile_prior_therapies as P  # noqa: E402


def one(text, **kw):
    r = P(text, **kw)
    assert len(r) == 1, f"expected 1 payload, got {len(r)}: {r}"
    return r[0]


def classes(r):
    return {p["drug_class"] for p in r}


class TestLineCounts:
    def test_max_lines(self):
        p = one("Participant must have had no more than 3 prior lines of therapy.")
        assert (p["drug_class"], p["max_lines"]) == ("ANY", 3)

    def test_no_more_than_is_a_cap_not_a_negation(self):
        # "NO more than 3 prior lines" says the patient HAS had prior therapy,
        # capped at 3. Reading the "no" as negation inverts the criterion.
        p = one("Participant must have had no more than 3 prior lines of therapy.")
        assert p["required"] is True

    def test_min_lines(self):
        p = one("Have progressed on at least 1 line of prior therapy "
                "for locally advanced/metastatic NSCLC")
        assert (p["min_lines"], p["progressed_on"]) == (1, True)
        assert p["setting"] == "advanced"

    def test_range_of_cycles_is_flagged_as_cycles(self):
        r = P("Received 3-4 cycles of neoadjuvant immunotherapy (PD-1 inhibitor) "
              "combined with chemotherapy.")
        assert all(p["count_unit"] == "cycles" for p in r)
        assert all((p["min_lines"], p["max_lines"]) == (3, 4) for p in r)
        assert all(p["setting"] == "neoadjuvant" for p in r)


class TestNaive:
    @pytest.mark.parametrize("text", [
        "Subjects must have treatment-naive unresectable stage III NSCLC",
        "Previously untreated locally advanced/metastatic lung adenocarcinoma",
    ])
    def test_naive_is_a_history_claim_without_a_named_class(self, text):
        p = one(text)
        assert (p["drug_class"], p["required"]) == ("ANY", False)

    def test_bare_untreated_is_not_a_therapy_claim(self):
        # "untreated" attaches to lesions far more often than to the patient.
        assert P("Active, untreated brain metastases") == []


class TestPolarity:
    def test_negation_sets_required_false(self):
        p = one("No prior systemic anti-cancer therapy for advanced NSCLC")
        assert p["required"] is False

    def test_splitter_flip_is_not_double_negated(self):
        # The splitter already turned this into an exclusion. The predicate must
        # assert the positive fact so that exclusion-MET blocks the patient.
        p = one("Participants must not have received prior therapy with "
                "docetaxel for this disease", polarity_flipped=True)
        assert (p["drug_class"], p["required"]) == ("CHEMOTHERAPY", True)


class TestWashoutBoundary:
    """A timed mention is a washout; only untimed claims are treatment history."""

    def test_timed_mention_is_suppressed(self):
        assert P("Prior radiotherapy within 2 weeks of the start of the study drug.",
                 timed_classes={"RADIOTHERAPY"}) == []

    def test_untimed_mention_still_compiles(self):
        assert classes(P("Prior treatment with cabozantinib")) == {"TKI"}

    def test_line_count_overrides_the_timed_suppression(self):
        # A count is a history requirement regardless of any window.
        r = P("Must have received no more than 2 prior chemotherapy regimens "
              "within 5 years", timed_classes={"CHEMOTHERAPY"})
        assert r and r[0]["max_lines"] == 2


class TestContextInheritance:
    def test_parent_header_supplies_the_cue(self):
        hdr = ("Patients who have received the following treatments "
               "must be excluded:",)
        r = P("Any systemic anti-tumor treatment, including radiotherapy;",
              context=hdr)
        assert "RADIOTHERAPY" in classes(r)


class TestRejections:
    @pytest.mark.parametrize("text", [
        "Prior solid organ or hematologic transplant",
        "Positive Pregnancy test (for women <61 years of age or without "
        "prior hysterectomy)",
        "Sign written informed consent prior to any study-related procedures",
        "History of hypersensitivity to active or inactive excipients "
        "of osimertinib",
        "Refractory nausea and vomiting or previous significant bowel resection",
    ])
    def test_prior_but_not_therapy(self, text):
        assert P(text) == []

    def test_prior_to_is_the_temporal_preposition(self):
        # "prior TO the first dose" is a window, not a treatment-history claim.
        assert P("Systemic anticancer therapy within 3 weeks prior to "
                 "the first dose") == []

    def test_future_therapy_is_not_prior_therapy(self):
        assert P("Participants with a known sensitizing molecular alteration "
                 "for which a Food and Drug Administration approved targeted "
                 "therapy for NSCLC exists") == []

    def test_radiation_pneumonitis_is_a_condition(self):
        assert P("Past medical history of ILD, drug-induced ILD, radiation "
                 "pneumonitis that required steroid treatment") == []


class TestToxicityGuard:
    def test_named_class_with_toxicity_is_still_prior_therapy(self):
        r = P("Has a history of any Grade 3 or 4 toxicities to a prior "
              "checkpoint inhibitor treatment")
        assert "CHECKPOINT_INHIBITOR" in classes(r)

    def test_generic_toxicity_recovery_is_not(self):
        assert P("Subjects who have recovered from all toxicities due to "
                 "prior therapy") == []
