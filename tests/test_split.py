"""Splitter tests. Written against layouts taken from the NSCLC corpus."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from split import header_kind, is_list_header, split_block  # noqa: E402


def texts(crits):
    return [c.raw_text for c in crits]


class TestSectionHeaders:
    def test_plain_headers(self):
        assert header_kind("Inclusion Criteria:") == "inclusion"
        assert header_kind("Exclusion Criteria:") == "exclusion"

    def test_decorated_headers(self):
        # These silently filed exclusions as inclusions before the fix.
        assert header_kind("Phase 1b Exclusion Criteria:") == "exclusion"
        assert header_kind("Exclusion Criteria (Part A)") == "exclusion"
        assert header_kind("Key Inclusion Criteria:") == "inclusion"
        assert header_kind("* Inclusion Criteria") == "inclusion"

    def test_sentences_about_criteria_are_not_headers(self):
        assert header_kind("Other inclusion/exclusion criteria may apply.") is None
        assert header_kind(
            "Participants meeting any exclusion criteria for this trial will be "
            "disqualified from entering the study."
        ) is None

    def test_section_switch_sets_polarity(self):
        block = ("Inclusion Criteria:\n1. Age >= 18 years\n\n"
                 "Phase 1b Exclusion Criteria:\n1. Active brain metastases\n")
        crits = split_block(block, "NCT0")
        by = {c.raw_text: c.is_inclusion for c in crits}
        assert by["Age >= 18 years"] is True
        assert by["Active brain metastases"] is False


class TestContinuationAcrossBlankLines:
    def test_indented_continuation_after_blank_line(self):
        # The predicate sits on a later line, indented under its marker, with a
        # blank line between. Splitting there orphans it from its analyte.
        block = (
            "6. Laboratory values as follows:\n"
            "\n"
            "   1. Absolute neutrophil count (ANC) >= 1500/mm3\n"
            "   2. Alanine aminotransferase (ALT) and aspartate aminotransferase (AST)\n"
            "\n"
            "      <= 3.0 x ULN if no liver involvement, or <= 5 x ULN with liver involvement\n"
            "   3. Platelets >= 100,000/mm3\n"
        )
        got = texts(split_block(block, "NCT0"))
        joined = [t for t in got if "Alanine" in t]
        assert len(joined) == 1
        assert "<= 3.0 x ULN" in joined[0], "continuation must rejoin its analyte"
        assert "<= 5 x ULN" in joined[0]
        assert not any(t.startswith("<=") for t in got), "no orphaned fragments"

    def test_sibling_marker_starts_a_new_criterion(self):
        block = ("   1. Platelets >= 100 x 10^9/L\n"
                 "   2. Hemoglobin >= 9 g/dL\n")
        assert len(split_block(block, "NCT0")) == 2


class TestListHeaders:
    def test_bare_header_is_structure_not_criterion(self):
        assert is_list_header("Adequate organ function:")
        assert is_list_header("Any of the following within 6 months "
                              "before the first dose of study treatment:")

    def test_colon_line_with_a_threshold_is_still_a_criterion(self):
        assert not is_list_header(
            "Serum creatinine <= 1.5 x ULN or creatinine clearance (CrCl) "
            ">= 30 mL/min. For estimation the Cockcroft-Gault equation "
            "should be used:"
        )

    def test_headers_are_dropped_and_attached_as_context(self):
        block = (
            "11. The subject has recent illness including the following conditions:\n"
            "\n"
            "    * Cardiovascular disorders including CHF\n"
            "    * Concurrent uncontrolled hypertension\n"
        )
        crits = split_block(block, "NCT0")
        assert len(crits) == 2, "the header itself is not a criterion"
        assert all("recent illness" in c.context[-1] for c in crits)

    def test_context_resets_when_indent_returns(self):
        block = (
            "6. Laboratory values as follows:\n"
            "\n"
            "   1. Platelets >= 100 x 10^9/L\n"
            "7. The subject is able to swallow tablets\n"
        )
        by = {c.raw_text: c.context for c in split_block(block, "NCT0")}
        assert by["Platelets >= 100 x 10^9/L"]
        assert by["The subject is able to swallow tablets"] == ()


class TestProsePolarity:
    def test_must_not_have_in_an_inclusion_section_is_an_exclusion(self):
        block = ("Inclusion Criteria:\n"
                 "1. Participants must not have received prior therapy with docetaxel\n")
        c = split_block(block, "NCT0")[0]
        assert c.is_inclusion is False
        assert c.polarity_flipped is True

    def test_plain_inclusion_is_untouched(self):
        block = ("Inclusion Criteria:\n"
                 "1. Participants must have recovered to grade 1\n")
        c = split_block(block, "NCT0")[0]
        assert c.is_inclusion is True
        assert c.polarity_flipped is False

    def test_raw_text_is_never_rewritten(self):
        block = ("Inclusion Criteria:\n"
                 "1. Participants must not be pregnant or breastfeeding\n")
        c = split_block(block, "NCT0")[0]
        assert c.raw_text == "Participants must not be pregnant or breastfeeding"


class TestBundledLines:
    def test_bundle_stays_one_criterion(self):
        # The compiler emits one predicate per analyte; splitting the text here
        # was lossy, so the criterion is kept whole.
        crits = split_block("1. ANC >=1.5x10^9/L, PLT >=100x10^9/L, Hb >=90g/L\n", "N")
        assert len(crits) == 1
