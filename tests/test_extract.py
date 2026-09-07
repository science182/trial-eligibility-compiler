"""Extraction tests: deterministic path, and the LLM path with a stub transport.

Nothing here needs a key or a network.
"""

import json
import sys
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "data" / "eval"))

import llm  # noqa: E402
from extract import (extract_conditions, extract_labs,  # noqa: E402
                     extract_rules, extract_therapies, find_dates, is_negated)

TODAY = date(2026, 8, 14)


class TestDemographics:
    @pytest.mark.parametrize("text,expected", [
        ("64-year-old female", 64),
        ("Age: 71 years", 71),
        ("aged 58", 58),
        ("A 45 yo man", 45),
    ])
    def test_age_forms(self, text, expected):
        assert extract_rules(text, TODAY).age.value == expected

    def test_ecog_forms(self):
        for t in ("ECOG performance status 1", "ECOG PS 1", "ECOG: 1",
                  "ECOG score of 1"):
            assert extract_rules(t, TODAY).ecog.value == 1

    def test_stage(self):
        assert extract_rules("stage IIIA NSCLC", TODAY).stage.value == "IIIA"
        assert extract_rules("Stage IV disease", TODAY).stage.value == "IV"

    def test_absent_fields_stay_none(self):
        p = extract_rules("Patient seen in clinic.", TODAY)
        assert p.age is None and p.ecog is None and p.stage is None


class TestLabs:
    def test_values_and_units_normalized(self):
        p = extract_rules(
            "ANC 2.6 x10^9/L, platelets 187 x10^9/L, hemoglobin 114 g/L, "
            "creatinine 0.9 mg/dL", TODAY)
        assert p.labs["ANC"].value == pytest.approx(2.6)
        assert p.labs["PLATELETS"].value == pytest.approx(187)
        assert p.labs["HEMOGLOBIN"].value == pytest.approx(11.4)   # g/L -> g/dL
        assert p.labs["CREATININE"].value == pytest.approx(0.9)

    def test_institutional_uln_is_not_stolen_by_the_previous_analyte(self):
        labs = extract_labs("total bilirubin 0.7 mg/dL, AST 31 U/L, "
                            "ALT 28 U/L (institutional ULN 40 U/L)")
        assert labs["BILIRUBIN"].uln is None
        assert labs["ALT"].uln == 40.0

    def test_hba1c_is_not_hemoglobin(self):
        assert "HEMOGLOBIN" not in extract_labs("hemoglobin A1C 7.2 %")

    def test_lab_spans_point_at_the_source(self):
        text = "Labs: ANC 2.6 x10^9/L today"
        p = extract_rules(text, TODAY)
        s, e = p.labs["ANC"].span
        assert "ANC 2.6" in text[s:e]


class TestNegation:
    def test_negation_reaches_the_whole_list(self):
        # The dangerous case: everything after the first item reading as PRESENT.
        text = "no pleural effusion, no pericardial effusion, no pneumonia"
        present, absent, _ = extract_conditions(text)
        assert present == []
        assert {"PLEURAL_EFFUSION", "PERICARDIAL_EFFUSION", "PNEUMONIA"} <= absent

    def test_chained_negation_after_a_single_cue(self):
        text = ("No investigational agent, live vaccine, antibiotics or "
                "surgery at any time prior.")
        _, _, never, _ = extract_therapies(text)
        assert {"INVESTIGATIONAL", "LIVE_VACCINE", "ANTIBIOTICS",
                "SURGERY"} <= never

    def test_trailing_negation(self):
        assert is_negated("HIV negative", 0, 3)

    def test_but_resets_the_scope(self):
        text = "No brain metastases but active infection present."
        present, absent, _ = extract_conditions(text)
        assert "BRAIN_METASTASES" in absent
        assert "ACTIVE_INFECTION" in {p.value for p in present}

    def test_sentence_boundary_limits_the_scope(self):
        text = "No brain metastases. Hypertension on amlodipine."
        present, absent, _ = extract_conditions(text)
        assert "BRAIN_METASTASES" in absent
        assert "HYPERTENSION" in {p.value for p in present}

    def test_stated_positive_outranks_a_later_generic_negative(self):
        text = "Comorbidities: hypertension. Review: no hypertension."
        present, _, _ = extract_conditions(text)
        assert "HYPERTENSION" in {p.value for p in present}


class TestBiomarkers:
    def test_positive_with_vaf(self):
        p = extract_rules("EGFR exon 19 deletion detected, VAF 31%", TODAY)
        b = p.biomarkers[0]
        assert (b.gene, b.alteration, b.vaf) == ("EGFR", "EXON19DEL", 31.0)

    def test_negative_genes_are_tested_but_not_present(self):
        p = extract_rules(
            "EGFR exon 19 deletion detected. ALK, ROS1: no alterations "
            "detected.", TODAY)
        assert {b.gene for b in p.biomarkers} == {"EGFR"}
        assert {"ALK", "ROS1"} <= p.genes_tested

    def test_untested_gene_is_neither(self):
        p = extract_rules("EGFR mutation detected", TODAY)
        assert "BRAF" not in p.genes_tested


class TestTherapies:
    def test_class_and_last_dose(self):
        t, last, _, _ = extract_therapies(
            "Carboplatin/pemetrexed 4 cycles, last dose 2026-07-28.")
        assert last["CHEMOTHERAPY"] == date(2026, 7, 28)

    def test_progression_detected(self):
        t, _, _, _ = extract_therapies(
            "osimertinib from 2025-04-02, progressed 2026-06-18 (RECIST PD)")
        assert t[0].drug_class == "EGFR_TKI" and t[0].progressed is True


class TestDates:
    def test_formats(self):
        got = [d for d, _ in find_dates(
            "2026-07-28 and 3/14/2025 and Mar 11, 2025")]
        assert date(2026, 7, 28) in got
        assert date(2025, 3, 14) in got
        assert date(2025, 3, 11) in got

    def test_invalid_dates_are_skipped(self):
        assert find_dates("2026-13-45") == []


class TestPersonaRoundTrip:
    def test_persona_extracts_completely(self):
        from loader import load_persona
        p = load_persona("maya_torres")
        assert p.age.value == 64
        assert p.stage.value == "IV"
        assert p.histology.value == "ADENOCARCINOMA"
        assert p.ecog.value == 1
        assert len(p.labs) >= 7
        assert p.has_condition("LIVER_METASTASES") is True
        assert p.has_condition("BRAIN_METASTASES") is False
        assert p.last_dose_dates["CHEMOTHERAPY"] == date(2026, 7, 28)
        assert p.therapy_history_complete is True

    def test_every_span_resolves(self):
        from loader import load_persona
        p = load_persona("maya_torres")
        for name, (s, e) in p.spans():
            assert p.report_text[s:e].strip(), name


# ------------------------------------------------------------- llm.py

class TestLLMChokepoint:
    def setup_method(self):
        llm.LOG.reset()

    def test_no_key_and_no_cache_raises_rather_than_guessing(self, monkeypatch):
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
        with pytest.raises(llm.LLMUnavailable):
            llm.complete("a prompt that is definitely not cached 8f3a")

    def test_stub_transport_logs_tokens_and_latency(self, monkeypatch, tmp_path):
        monkeypatch.setenv("GEMINI_API_KEY", "test-key")
        monkeypatch.setattr(llm, "CACHE_DIR", tmp_path)
        monkeypatch.setattr(llm, "LOG_PATH", tmp_path / "calls.jsonl")
        monkeypatch.setattr(llm, "TRANSPORT",
                            lambda m, p, s, t, to: ('{"ok": true}', 120, 8))
        out = llm.complete("extract this", model="stub")
        assert out == '{"ok": true}'
        assert llm.LOG.summary()["total_tokens"] == 128
        assert llm.LOG.summary()["network_calls"] == 1

    def test_second_identical_call_is_served_from_cache(self, monkeypatch,
                                                        tmp_path):
        monkeypatch.setenv("GEMINI_API_KEY", "test-key")
        monkeypatch.setattr(llm, "CACHE_DIR", tmp_path)
        monkeypatch.setattr(llm, "LOG_PATH", tmp_path / "calls.jsonl")
        calls = []

        def stub(m, p, s, t, to):
            calls.append(p)
            return '{"ok": true}', 10, 2

        monkeypatch.setattr(llm, "TRANSPORT", stub)
        llm.complete("same prompt", model="stub")
        llm.complete("same prompt", model="stub")
        assert len(calls) == 1, "the demo path must not re-hit the network"
        assert llm.LOG.summary()["cached_calls"] == 1

    def test_json_helper_strips_code_fences(self, monkeypatch, tmp_path):
        monkeypatch.setenv("GEMINI_API_KEY", "test-key")
        monkeypatch.setattr(llm, "CACHE_DIR", tmp_path)
        monkeypatch.setattr(llm, "LOG_PATH", tmp_path / "calls.jsonl")
        monkeypatch.setattr(llm, "TRANSPORT",
                            lambda *a: ('```json\n{"age": 64}\n```', 5, 5))
        assert llm.complete_json("p", model="stub") == {"age": 64}

    def test_bad_json_fails_closed(self, monkeypatch, tmp_path):
        monkeypatch.setenv("GEMINI_API_KEY", "test-key")
        monkeypatch.setattr(llm, "CACHE_DIR", tmp_path)
        monkeypatch.setattr(llm, "LOG_PATH", tmp_path / "calls.jsonl")
        monkeypatch.setattr(llm, "TRANSPORT", lambda *a: ("not json", 1, 1))
        with pytest.raises(ValueError):
            llm.complete_json("p", model="stub")


class TestExtractDegradesGracefully:
    def test_llm_failure_falls_back_to_rules(self, monkeypatch):
        from extract import extract
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
        rec, used = extract("64-year-old female, ECOG 1", TODAY, use_llm=True)
        assert used is False
        assert rec.age.value == 64          # the page still renders
