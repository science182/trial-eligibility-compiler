"""Golden-file test: fixed persona against fixed trials, expected output committed.

Section 10: "Run it before every demo rehearsal." This is the regression net for
the whole pipeline -- split, compile, evaluate, aggregate -- so any change that
moves a trial between buckets shows up here rather than on stage.

Regenerate deliberately after an intended behaviour change:
    python3 tests/test_golden.py --update
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from aggregate import assess_trial  # noqa: E402
from evaluate import Verdict  # noqa: E402
from loader import load_corpus, load_persona  # noqa: E402

GOLDEN = ROOT / "tests" / "golden_maya_torres.json"

# Fifty fixed trials, taken in corpus order so the set is stable.
N_TRIALS = 50


def _snapshot():
    compiled, _ = load_corpus()
    patient = load_persona("maya_torres")
    ids = sorted(compiled)[:N_TRIALS]

    out = {}
    for tid in ids:
        a = assess_trial(tid, compiled[tid], patient)
        counts = {v.value: 0 for v in Verdict}
        for r in a.results:
            counts[r.verdict.value] += 1
        out[tid] = {
            "state": a.state.value,
            "eligible_date": a.eligible_date.isoformat() if a.eligible_date else None,
            "blocking_reason": a.blocking_reason,
            "missing_fields": list(a.missing_fields),
            "verdicts": counts,
        }
    return out


def test_golden_output_is_unchanged():
    assert GOLDEN.exists(), "run: python3 tests/test_golden.py --update"
    expected = json.loads(GOLDEN.read_text())
    actual = _snapshot()

    assert set(actual) == set(expected), "trial set changed"
    drift = {
        tid: {"expected": expected[tid], "actual": actual[tid]}
        for tid in expected if actual[tid] != expected[tid]
    }
    assert not drift, (
        f"{len(drift)} trial(s) changed state or reason:\n"
        + json.dumps(drift, indent=2)[:3000]
    )


def test_patient_spans_all_resolve():
    """Provenance must survive: every span points at real report text."""
    p = load_persona("maya_torres")
    spans = p.spans()
    assert len(spans) >= 15
    for name, span in spans:
        assert isinstance(span, tuple) and len(span) == 2, name
        s, e = span
        assert 0 <= s < e <= len(p.report_text), name
        assert p.report_text[s:e].strip(), name


if __name__ == "__main__":
    if "--update" in sys.argv:
        GOLDEN.write_text(json.dumps(_snapshot(), indent=1, sort_keys=True) + "\n")
        print(f"wrote {GOLDEN}")
    else:
        print("pass --update to regenerate")
