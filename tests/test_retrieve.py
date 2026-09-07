"""Retrieval component tests."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from retrieve import BM25, order, rrf, tokenize  # noqa: E402

DOCS = [
    "advanced non-small cell lung cancer with EGFR exon 19 deletion",
    "metastatic colorectal cancer previously treated with fluorouracil",
    "early stage breast cancer adjuvant endocrine therapy",
    "NSCLC osimertinib resistance EGFR T790M progression",
]


class TestTokenize:
    def test_lowercases_and_drops_stopwords(self):
        assert "the" not in tokenize("The Patient")
        assert "patient" not in tokenize("The Patient")

    def test_keeps_alphanumeric_terms(self):
        assert "egfr" in tokenize("EGFR exon 19")
        assert "19" in tokenize("EGFR exon 19")


class TestBM25:
    def setup_method(self):
        self.bm = BM25([tokenize(d) for d in DOCS])

    def test_ranks_the_matching_document_first(self):
        top = order(self.bm.scores("EGFR exon 19 deletion lung cancer"))[0]
        assert top == 0

    def test_unrelated_query_scores_low(self):
        s = self.bm.scores("breast cancer endocrine")
        assert order(s)[0] == 2

    def test_unknown_terms_do_not_crash(self):
        assert len(self.bm.scores("zzzzz qqqqq")) == len(DOCS)

    def test_scores_are_non_negative(self):
        assert all(x >= 0 for x in self.bm.scores("cancer lung"))

    def test_every_document_gets_a_score(self):
        assert len(self.bm.scores("cancer")) == len(DOCS)


class TestRRF:
    def test_documents_ranked_well_by_both_arms_win(self):
        a = ["x", "y", "z"]
        b = ["x", "z", "y"]
        assert rrf([a, b])[0] == "x"

    def test_fuses_disjoint_rankings(self):
        assert set(rrf([["a", "b"], ["c", "d"]])) == {"a", "b", "c", "d"}

    def test_rank_based_so_score_scales_do_not_matter(self):
        # RRF sees only positions, which is why the arms need no calibration.
        assert rrf([["p", "q"]]) == ["p", "q"]
