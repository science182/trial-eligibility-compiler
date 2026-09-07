"""LAB_THRESHOLD compiler tests, written against text taken from the corpus."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from compile import compile_lab_thresholds as C  # noqa: E402


def one(text):
    r = C(text)
    assert len(r) == 1, f"expected 1 predicate, got {len(r)}: {r}"
    return r[0]


def sig(p):
    return (p["analyte"], p["operator"], p["value"], p["unit"], p["condition"])


class TestBasicExtraction:
    def test_anc(self):
        p = one("Absolute neutrophil count (ANC) >= 1.5 x 10^9/L")
        assert sig(p) == ("ANC", ">=", 1.5, "10^9/L", None)

    def test_registry_escaped_operators(self):
        assert one(r"Hemoglobin \>= 9.0 g/dL")["operator"] == ">="
        assert one(r"Total bilirubin =\< 1.5 mg/dL")["operator"] == "<="

    def test_word_operators(self):
        assert one("Absolute neutrophil count at least 1.5 x 10^9/L")["operator"] == ">="
        assert one("Total bilirubin no more than 1.5 mg/dL")["operator"] == "<="
        assert one("Hemoglobin greater than 9 g/dL")["operator"] == ">"

    def test_uln_relative(self):
        p = one("Total bilirubin <= 1.5 x institutional upper limit of normal (ULN)")
        assert p["basis"] == "uln"
        assert p["value"] == 1.5
        assert p["unit"] == "ULN"

    def test_bare_uln_is_multiplier_one(self):
        p = one("ALT <= ULN")
        assert p["basis"] == "uln" and p["value"] == 1.0

    def test_unicode_operators_and_superscripts(self):
        p = one("Absolute neutrophil count ≥1.5×10⁹/L")
        assert sig(p) == ("ANC", ">=", 1.5, "10^9/L", None)


class TestMultiplePredicates:
    def test_shared_threshold_binds_both_analytes(self):
        r = C("AST and ALT <= 2.5 x ULN")
        assert {p["analyte"] for p in r} == {"AST", "ALT"}
        assert all(p["value"] == 2.5 for p in r)

    def test_bundled_line_splits_per_analyte(self):
        r = C("ANC ≥1.5×10⁹/L, LYM ≥0.5×10⁹/L, PLT ≥100×10⁹/L, Hb ≥90g/L")
        got = {(p["analyte"], p["value"]) for p in r}
        assert got == {("ANC", 1.5), ("LYMPHOCYTES", 0.5),
                       ("PLATELETS", 100.0), ("HEMOGLOBIN", 9.0)}

    def test_dual_unit_restatement_collapses_to_one(self):
        # "1,500/mm3" and "1.5 x 10^9/L" are the same threshold written twice.
        r = C("Absolute Neutrophil Count (ANC) >= 1,500/mm3 or >=1.5 x 109/L")
        assert len(r) == 1
        assert r[0]["value"] == pytest.approx(1.5)


class TestDisjunctionGrouping:
    def test_or_across_analytes_shares_a_group(self):
        r = C("Creatinine <=1.5 x ULN or creatinine clearance (CrCl) >= 40 mL/min")
        assert len({p["group"] for p in r}) == 1, "OR alternatives must share a group"

    def test_and_across_analytes_splits_groups(self):
        r = C("Serum creatinine <= 1.5 x ULN and creatinine clearance >= 60 ml/min")
        assert len({p["group"] for p in r}) == 2, "AND requirements are separate groups"

    def test_comma_list_splits_groups(self):
        r = C("ANC ≥1.5×10⁹/L, PLT ≥100×10⁹/L")
        assert len({p["group"] for p in r}) == 2


class TestConditionalVariants:
    def test_parenthesised_liver_variant(self):
        r = C("AST and ALT <= 2.5 x ULN (<=5.0 x ULN in case of liver metastases).")
        base = [p for p in r if p["condition"] is None]
        var = [p for p in r if p["condition"] == "liver_metastases"]
        assert len(base) == 2 and len(var) == 2
        assert all(p["value"] == 2.5 for p in base)
        assert all(p["value"] == 5.0 for p in var)

    def test_if_no_liver_or_with_liver(self):
        r = C("ALT and AST <= 2.5 x ULN if no liver involvement "
              "or <= 5 x ULN with liver involvement")
        by = {(p["analyte"], p["condition"]): p["value"] for p in r}
        assert by[("ALT", "no_liver_metastases")] == 2.5
        assert by[("ALT", "liver_metastases")] == 5.0

    def test_unless_clause_qualifies_the_variant_not_the_base(self):
        r = C("Total bilirubin <= 1.5 x ULN unless history of Gilberts disease, "
              "then <= 3.0 mg/dL")
        base = [p for p in r if p["condition"] is None]
        var = [p for p in r if p["condition"] == "gilberts"]
        assert len(base) == 1 and base[0]["value"] == 1.5
        assert len(var) == 1 and var[0]["value"] == 3.0


class TestRejections:
    """False positives here are worse than misses: they produce confident errors."""

    @pytest.mark.parametrize("text", [
        "Male: CrCl (mL/min) = (140 - age) x wt (kg) / (serum creatinine x 72) Female:",
        "Males: Creatinine CL (mL/min) = Weight (kg) x (140 - Age) 72 x serum creatinine",
        "Multiply above result by 0.85",
        "72 x serum creatinine in mg/dL",
    ])
    def test_cockcroft_gault_formula_is_not_a_threshold(self, text):
        assert C(text) == []

    def test_hba1c_is_not_hemoglobin(self):
        assert C("Uncontrolled diabetes mellitus with hemoglobin (Hgb) A1C >=10.0%.") == []

    def test_washout_durations_are_not_labs(self):
        assert C("Monoclonal antibodies: >= 5 half-lives or >= 42 days, "
                 "whichever is longer.") == []

    def test_toxicity_grades_are_not_labs(self):
        assert C("Patient not recovered to <= Grade 1 from AEs") == []
        assert C("Platelet toxicity <= grade 2") == []

    def test_prose_without_numbers(self):
        assert C("Adequate hematologic function") == []
        assert C("The use of platelet transfusion to meet these criteria "
                 "is not permitted.") == []

    def test_no_analyte_no_predicate(self):
        assert C("PD-L1 tumor expression >= 1%") == []


class TestProvenance:
    def test_raw_value_and_unit_are_preserved(self):
        p = one("Hemoglobin >= 90 g/L")
        assert p["value"] == 9.0 and p["unit"] == "g/dL"     # normalized
        assert p["raw_value"] == 90 and p["raw_unit"] == "g/L"  # as written
