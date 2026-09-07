"""AGE, PERFORMANCE_STATUS, HISTOLOGY, STAGE, BIOMARKER compiler tests.

All source strings are taken from the 500-trial NSCLC corpus.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from compile import (compile_age, compile_biomarkers,  # noqa: E402
                     compile_histology, compile_performance_status,
                     compile_stage)
from onco import expand_stage_range  # noqa: E402


def one(fn, text):
    r = fn(text)
    assert len(r) == 1, f"expected 1 payload, got {len(r)}: {r}"
    return r[0]


# ------------------------------------------------------------------- AGE

class TestAge:
    @pytest.mark.parametrize("text,lo,hi", [
        ("Age >= 18 years.", 18, None),
        ("Age: >= 18 years", 18, None),
        ("Male or female, 18 years of age or older", 18, None),
        ("18 years old or older.", 18, None),
        ("Age 70 years or older, regardless of sex.", 70, None),
        ("Aged >=18 years and <=75 years, regardless of gender;", 18, 75),
        ("Age from 18 to 80 years old;", 18, 80),
        ("Between the ages of 18 and 75;", 18, 75),
        ("At least 18 years and no older than 85 years (including 85 years "
         "old) at the time of signing the ICF.", 18, 85),
    ])
    def test_bounds(self, text, lo, hi):
        p = one(compile_age, text)
        assert (p["min_years"], p["max_years"]) == (lo, hi)

    def test_operator_written_after_the_number(self):
        # "Aged 18 >= years." appears verbatim in the corpus.
        assert one(compile_age, "Aged 18 >= years.")["min_years"] == 18

    @pytest.mark.parametrize("text", [
        "Men and women of reproductive age agree to contraception",
        "People of childbearing age",
        "Males: Mass(kg) x (140-Age) / 72",
        "Life expectancy of at least 6 months",
    ])
    def test_rejections(self, text):
        assert compile_age(text) == []


# ------------------------------------------------- PERFORMANCE_STATUS

class TestPerformanceStatus:
    @pytest.mark.parametrize("text,lo,hi", [
        ("ECOG Performance Status (PS) of 0-1.", 0, 1),
        ("ECOG score is 0 or 1;", 0, 1),
        ("Eastern Cooperative Oncology Group (ECOG) performance status 0-2", 0, 2),
        ("Participants must have an ECOG PS of 0 to 2.", 0, 2),
        ("ECOG performance status <= 3", 0, 3),
    ])
    def test_ecog_ranges(self, text, lo, hi):
        p = one(compile_performance_status, text)
        assert p["scale"] == "ECOG"
        assert (p["min_value"], p["max_value"]) == (lo, hi)

    def test_value_stated_before_the_scale_name(self):
        p = one(compile_performance_status,
                "Have a performance status of 0 on the Eastern Cooperative "
                "Oncology Group (ECOG) Performance Status within 7 days "
                "prior to the first dose")
        assert (p["min_value"], p["max_value"]) == (0, 0)

    def test_exclusion_operator_is_preserved_not_flipped(self):
        # "ECOG > 1" as an exclusion asserts PS > 1; storing max_value=1 would
        # invert the meaning.
        p = one(compile_performance_status, "ECOG performance status >1.")
        assert p["operator"] == ">" and p["value"] == 1

    def test_karnofsky_is_a_minimum(self):
        p = one(compile_performance_status,
                "Karnofsky performance status of at least 60")
        assert p["scale"] == "KARNOFSKY" and p["min_value"] == 60

    def test_asa_roman_range(self):
        p = one(compile_performance_status,
                "American Society of Anesthesiologists physical status (ASA) I-III")
        assert (p["scale"], p["min_value"], p["max_value"]) == ("ASA", 1, 3)

    def test_no_scale_no_predicate(self):
        assert compile_performance_status("Adequate organ function") == []


# ------------------------------------------------------------- HISTOLOGY

class TestHistology:
    def test_confirmed_nsclc(self):
        p = one(compile_histology,
                "Histologically or cytologically confirmed non-small cell "
                "lung cancer (NSCLC).")
        assert p["allowed_codes"] == ["NSCLC"]

    def test_subtype_needs_no_cue(self):
        p = one(compile_histology, "Stage IV non-squamous NSCLC.")
        assert "NSCLC_NONSQUAMOUS" in p["allowed_codes"]

    def test_sclc_is_always_excluded(self):
        p = one(compile_histology, "Patients with small cell lung cancer;")
        assert p["excluded_codes"] == ["SCLC"]

    def test_mixed_sclc_excludes_only_the_component(self):
        # "NSCLC with mixed SCLC" disqualifies the SCLC component. The "mixed"
        # cue belongs to the first clause and must not reach the second
        # mention of NSCLC after "or".
        p = one(compile_histology,
                "NSCLC with mixed small cell lung cancer (SCLC) or NSCLC "
                "with histologic SCLC transformation.")
        assert p["excluded_codes"] == ["SCLC"]
        assert p["allowed_codes"] == ["NSCLC"]

    def test_cue_after_the_term(self):
        p = one(compile_histology,
                "Non-small cell lung cancer confirmed by histopathology "
                "or cytology, clinical stage II")
        assert p["allowed_codes"] == ["NSCLC"]

    @pytest.mark.parametrize("text", [
        "except adequately treated basal cell or squamous cell skin cancer",
        "Head and neck squamous cell carcinoma",
        "Diagnosis of any malignancy other than non-small cell lung cancer "
        "within 5 years",
    ])
    def test_other_diseases_are_not_this_tumour(self, text):
        assert compile_histology(text) == []

    def test_background_mention_is_not_a_requirement(self):
        # NSCLC named as context for prior therapy, not as a histology claim.
        assert compile_histology(
            "Prior thoracic radiotherapy or prior systemic treatment "
            "for stage IIIB/IV NSCLC") == []


# ----------------------------------------------------------------- STAGE

class TestStage:
    def test_single_stage(self):
        p = one(compile_stage, "De novo stage IV or recurrent NSCLC")
        assert p["allowed_stages"] == ["IV"]

    def test_explicit_list(self):
        p = one(compile_stage, "Clinical stage II, IIIA, or IIIB "
                               "(limited to resectable N2)")
        assert p["allowed_stages"] == ["II", "IIIA", "IIIB"]

    def test_range_expansion(self):
        p = one(compile_stage, "Histologically confirmed stage II-IIIB NSCLC")
        assert p["allowed_stages"] == ["II", "IIA", "IIB", "III", "IIIA", "IIIB"]

    def test_bare_endpoint_covers_its_substages(self):
        # "I-III" must reach IIIC, not stop at bare III.
        assert "IIIC" in expand_stage_range("I", "III")
        assert "IV" not in expand_stage_range("I", "III")

    def test_descriptor_mapping_is_flagged(self):
        p = one(compile_stage, "locally advanced or metastatic, not suitable "
                               "for curative therapy")
        assert p["from_descriptor"] is True
        assert "IV" in p["allowed_stages"] and "III" in p["allowed_stages"]

    def test_therapy_context_is_not_a_stage_requirement(self):
        assert compile_stage(
            "Prior systemic treatment for stage IIIB/IV NSCLC") == []

    def test_no_stage_no_predicate(self):
        assert compile_stage("Adequate organ function") == []


# ------------------------------------------------------------- BIOMARKER

class TestBiomarker:
    def test_specific_alterations_beat_the_generic_noun(self):
        r = compile_biomarkers("EGFR sensitizing mutations "
                               "(Exon19del and/or L858R) are required")
        assert {p["alteration"] for p in r} == {"EXON19DEL", "L858R"}
        assert all(p["gene"] == "EGFR" and p["required"] for p in r)

    def test_each_variant_in_a_list(self):
        r = compile_biomarkers("evidence of a single KRAS G12C, G12D, G12V "
                               "mutation in tumor tissue")
        assert {p["alteration"] for p in r} == {"G12C", "G12D", "G12V"}

    def test_gene_list_shares_a_trailing_alteration(self):
        r = compile_biomarkers("Tumor with known EGFR, ALK, ROS1, MET or RET "
                               "mutations/fusions")
        assert {p["gene"] for p in r} == {"EGFR", "ALK", "ROS1", "MET", "RET"}

    def test_negation_sets_required_false(self):
        r = compile_biomarkers("No EGFR sensitive mutations or ALK gene "
                               "translocations.")
        assert all(p["required"] is False for p in r)

    def test_wild_type_is_absence(self):
        p = one(compile_biomarkers,
                "For NSCLC (EGFR wild type) with adenocarcinoma histology")
        assert (p["gene"], p["required"]) == ("EGFR", False)

    def test_positive_marker(self):
        p = one(compile_biomarkers,
                "Pathologically confirmed diagnosis of ALK-positive NSCLC")
        assert (p["gene"], p["alteration"], p["required"]) == (
            "ALK", "POSITIVE", True)

    def test_met_does_not_match_the_word_met(self):
        assert compile_biomarkers(
            "Participants must have demonstrated progression and have met "
            "the criteria for mutation review") == [] or all(
            p["gene"] != "MET" for p in compile_biomarkers(
                "Participants have met the criteria"))

    def test_fusion_protein_is_not_a_gene_fusion(self):
        assert compile_biomarkers(
            "History of severe allergic reactions to chimeric or humanized "
            "antibodies or fusion proteins") == []

    def test_alterations_do_not_cross_genes(self):
        r = compile_biomarkers("KRAS G12C mutation and EGFR L858R mutation")
        by = {p["gene"]: p["alteration"] for p in r}
        assert by["KRAS"] == "G12C" and by["EGFR"] == "L858R"
