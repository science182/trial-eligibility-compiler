"""UI payload tests. Exercise the server's JSON contract without a browser."""

import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "data" / "eval"))
sys.path.insert(0, str(ROOT / "ui"))

import pytest  # noqa: E402

from personas import MAYA_TORRES  # noqa: E402


@pytest.fixture(scope="module")
def payload():
    from app import assess_payload
    return assess_payload(MAYA_TORRES["report"], MAYA_TORRES["index_date"])


class TestContract:
    def test_all_four_buckets_are_represented(self, payload):
        states = {t["state"] for t in payload["trials"]}
        assert {"eligible_now", "eligible_on_date", "undetermined",
                "blocked"} <= states

    def test_no_model_calls(self, payload):
        assert payload["timing"]["model_calls"] == 0

    def test_renders_fast_enough_for_the_demo(self, payload):
        """The spec budgets under three seconds for the whole render.

        Asserted against the spec's own budget, not against the ~65ms this
        actually takes on an idle machine. A tighter bound turns a busy CPU
        into a red test, and the one moment this suite runs is the pre-flight
        before recording -- with a server and a browser already running. A
        performance guard that cries wolf exactly then is worse than none.
        The real number is tracked by eval/differentiation.py, which reports a
        median over 20 runs instead of asserting on a single sample.
        """
        assert payload["timing"]["total_ms"] < 3000

    def test_trials_are_ranked_best_first(self, payload):
        order = ["eligible_now", "eligible_on_date", "undetermined", "blocked"]
        seen = [order.index(t["state"]) for t in payload["trials"]]
        assert seen == sorted(seen)


class TestProvenance:
    def test_every_row_span_lands_inside_the_report(self, payload):
        report = payload["patient"]["report"]
        n = 0
        for t in payload["trials"]:
            for r in t["rows"]:
                for s, e in r["spans"]:
                    assert 0 <= s < e <= len(report)
                    assert report[s:e].strip()
                    n += 1
        assert n > 50, "click-to-highlight would be mostly dead"

    def test_the_dated_trial_row_points_at_its_anchor(self, payload):
        dated = [t for t in payload["trials"]
                 if t["state"] == "eligible_on_date"][0]
        pend = [r for r in dated["rows"] if r["verdict"] == "pending"][0]
        report = payload["patient"]["report"]
        assert pend["spans"], "the pending row must highlight something"
        assert pend["eligible_date"] and pend["anchor_date"]
        assert any(report[s:e].strip() for s, e in pend["spans"])

    def test_extracted_summary_is_populated(self, payload):
        p = payload["patient"]
        assert p["age"] == 64 and p["stage"] == "IV" and p["ecog"] == 1
        assert "EGFR EXON19DEL" in p["biomarkers"]


class TestPanels:
    def test_calendar_has_a_dated_opening(self, payload):
        assert payload["calendar"]
        assert payload["calendar"][0]["date"] >= payload["patient"]["index_date"]

    def test_missing_headline_uses_a_union_not_a_max(self, payload):
        h = payload["missing_headline"]
        rows = payload["missing"][:4]
        assert h["trials"] >= max(r["trials"] for r in rows)
        assert h["criteria"] == sum(r["criteria"] for r in rows)


class TestRows:
    def test_rows_are_worst_first(self, payload):
        order = ["not_met", "pending", "undetermined", "met"]
        for t in payload["trials"][:40]:
            seen = [order.index(r["verdict"]) for r in t["rows"]]
            assert seen == sorted(seen)

    def test_free_text_criteria_are_not_shown_as_rows(self, payload):
        for t in payload["trials"]:
            assert all(r["type"] != "FREE_TEXT" for r in t["rows"])

    def test_every_row_carries_its_source_sentence(self, payload):
        for t in payload["trials"][:20]:
            for r in t["rows"]:
                assert r["raw_text"].strip()


class TestBadInput:
    def test_empty_report_does_not_crash_the_extractor(self):
        from app import assess_payload
        d = assess_payload("no clinical content here", date(2026, 8, 14))
        assert d["timing"]["trials"] == 500
        assert all(t["state"] in ("undetermined", "blocked")
                   for t in d["trials"]), "nothing should look eligible"


class TestPersonaRebasing:
    """The served fixture must never announce a date that has already passed.

    The persona is pinned to a fixed index date so tests and the eval stay
    deterministic. Serving it unchanged means the public demo keeps saying
    "eligible in 11 days" long after that day is gone, which contradicts the
    one claim the product leads with.
    """

    def test_rebasing_lands_the_index_date_on_today(self):
        from service import rebase_persona
        r = rebase_persona(MAYA_TORRES)
        assert r["index_date"] == date.today()

    def test_rebasing_preserves_every_interval(self):
        from datetime import timedelta
        from service import rebase_persona
        target = date.today() + timedelta(days=97)
        r = rebase_persona(MAYA_TORRES, today=target)
        delta = (target - MAYA_TORRES["index_date"]).days
        for iso in re.findall(r"\d{4}-\d{2}-\d{2}", MAYA_TORRES["report"]):
            moved = (date.fromisoformat(iso) + timedelta(days=delta)).isoformat()
            assert moved in r["report"], f"{iso} did not shift to {moved}"

    def test_rebasing_changes_no_verdict(self):
        from service import assess_payload, rebase_persona
        from loader import load_corpus
        compiled, meta = load_corpus()

        def state(p):
            out = assess_payload(compiled, meta, p["report"], p["index_date"])
            counts = {}
            for t in out["trials"]:
                counts[t["state"]] = counts.get(t["state"], 0) + 1
            idx = date.fromisoformat(out["patient"]["index_date"])
            offsets = {t["id"]: (date.fromisoformat(t["eligible_date"]) - idx).days
                       for t in out["trials"] if t["eligible_date"]}
            return counts, offsets

        assert state(MAYA_TORRES) == state(rebase_persona(MAYA_TORRES))

    def test_served_dates_are_in_the_future(self):
        from service import assess_payload, rebase_persona
        from loader import load_corpus
        compiled, meta = load_corpus()
        r = rebase_persona(MAYA_TORRES)
        out = assess_payload(compiled, meta, r["report"], r["index_date"])
        dated = [t for t in out["trials"] if t["eligible_date"]]
        assert dated, "the demo needs at least one dated trial"
        for t in dated:
            assert date.fromisoformat(t["eligible_date"]) > date.today(), t["id"]


class TestLocalDate:
    """The server runs in UTC; the visitor does not.

    Vercel returned an index date one day ahead of the local date, on a product
    whose central claim is date accuracy. The browser sends its own date and the
    server accepts it only when it is plausible.
    """

    def test_accepts_a_plausible_local_date(self):
        from datetime import timedelta
        from service import parse_local_date
        for offset in (-1, 0, 1):
            d = date.today() + timedelta(days=offset)
            assert parse_local_date(d.isoformat()) == d

    def test_rejects_an_implausible_or_malformed_date(self):
        from datetime import timedelta
        from service import parse_local_date
        assert parse_local_date(None) is None
        assert parse_local_date("") is None
        assert parse_local_date("not-a-date") is None
        assert parse_local_date("2026-13-45") is None
        # Beyond any real timezone offset: ignored rather than trusted.
        assert parse_local_date((date.today() + timedelta(days=400)).isoformat()) is None
        assert parse_local_date((date.today() - timedelta(days=400)).isoformat()) is None

    def test_a_supplied_date_drives_the_rebase(self):
        from datetime import timedelta
        from service import parse_local_date, rebase_persona
        wanted = date.today() - timedelta(days=1)      # a visitor west of UTC
        r = rebase_persona(MAYA_TORRES, parse_local_date(wanted.isoformat()))
        assert r["index_date"] == wanted
