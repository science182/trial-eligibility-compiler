"""Unit conversion tests. Section 10 requires these explicitly."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from units import UnitError, clean_unit, find_analyte, to_canonical  # noqa: E402


class TestCellCounts:
    """ANC/platelets: cells/uL vs 10^9/L is the classic 1000x trap."""

    @pytest.mark.parametrize("value,unit,expected", [
        (1.5, "10^9/L", 1.5),
        (1500, "/mm3", 1.5),
        (1500, "cells/mm3", 1.5),
        (1500, "/uL", 1.5),
        (1500, "/µL", 1.5),
        (1.5, "10^3/uL", 1.5),      # 10^3/uL == 10^9/L exactly
        (1.5, "x10^9/L", 1.5),
        (1.5, "109/L", 1.5),        # registry strips the superscript
        (1.5, "10⁹/L", 1.5),
    ])
    def test_anc_all_spellings_agree(self, value, unit, expected):
        got, canon = to_canonical("ANC", value, unit)
        assert got == pytest.approx(expected)
        assert canon == "10^9/L"

    @pytest.mark.parametrize("value,unit,expected", [
        (100, "10^9/L", 100.0),
        (100000, "/mm3", 100.0),
        (100000, "/uL", 100.0),
        (100, "10^3/uL", 100.0),
    ])
    def test_platelets(self, value, unit, expected):
        assert to_canonical("PLATELETS", value, unit)[0] == pytest.approx(expected)

    def test_unitless_count_inferred_by_magnitude(self):
        # "ANC >= 1.5" and "ANC >= 1500" mean the same threshold.
        assert to_canonical("ANC", 1.5, "")[0] == pytest.approx(1.5)
        assert to_canonical("ANC", 1500, "")[0] == pytest.approx(1.5)
        assert to_canonical("PLATELETS", 100, "")[0] == pytest.approx(100.0)
        assert to_canonical("PLATELETS", 100000, "")[0] == pytest.approx(100.0)


class TestHemoglobin:
    @pytest.mark.parametrize("value,unit,expected", [
        (9.0, "g/dL", 9.0),
        (90, "g/L", 9.0),
        (12.0, "g/dL", 12.0),
        (120, "g/L", 12.0),
    ])
    def test_hemoglobin_gdl_vs_gl(self, value, unit, expected):
        got, canon = to_canonical("HEMOGLOBIN", value, unit)
        assert got == pytest.approx(expected)
        assert canon == "g/dL"


class TestCreatinine:
    @pytest.mark.parametrize("value,unit,expected", [
        (1.5, "mg/dL", 1.5),
        (132.6, "umol/L", 1.5),     # 132.6 / 88.4
        (132.6, "µmol/L", 1.5),
        (88.4, "umol/L", 1.0),
    ])
    def test_creatinine_mgdl_vs_umoll(self, value, unit, expected):
        got = to_canonical("CREATININE", value, unit)[0]
        assert got == pytest.approx(expected, rel=1e-3)

    def test_bilirubin_umol(self):
        assert to_canonical("BILIRUBIN", 17.104, "umol/L")[0] == pytest.approx(1.0, rel=1e-3)


class TestRefusalToGuess:
    """An unconvertible unit must raise, never silently pass a wrong number."""

    def test_unknown_unit_raises(self):
        with pytest.raises(UnitError):
            to_canonical("HEMOGLOBIN", 9.0, "furlongs")

    def test_unknown_analyte_raises(self):
        with pytest.raises(UnitError):
            to_canonical("UNOBTAINIUM", 1.0, "g/dL")

    def test_molar_without_table_entry_raises(self):
        with pytest.raises(UnitError):
            to_canonical("AST", 40, "umol/L")


class TestCleanUnit:
    @pytest.mark.parametrize("raw,expected", [
        ("10\\^9/L", "10^9/l"),
        ("x10^9/L", "10^9/l"),
        ("10⁹/L", "10^9/l"),
        ("109/L", "10^9/l"),
        ("cells/mm3", "/mm3"),
        ("/µL", "/ul"),
        ("mL/min", "ml/min"),
        (" g / dL ", "g/dl"),
    ])
    def test_clean_unit(self, raw, expected):
        assert clean_unit(raw) == expected


class TestAnalyteDetection:
    def test_longest_match_wins(self):
        assert find_analyte("creatinine clearance >= 60")[0] == "CREATININE_CLEARANCE"
        assert find_analyte("serum creatinine <= 1.5")[0] == "CREATININE"

    def test_hba1c_is_not_hemoglobin(self):
        assert find_analyte("hemoglobin A1C >= 10.0%")[0] != "HEMOGLOBIN"

    def test_absolute_neutrophil_count(self):
        assert find_analyte("Absolute neutrophil count (ANC) >= 1.5")[0] == "ANC"
