"""Load the compiled trial corpus and persona fixtures.

Compiling all 500 trials takes a few seconds, so the result is cached to
data/compiled/. The online path reads the cache; nothing at query time re-runs
the compiler.
"""

import json
import pickle
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "data" / "eval"))

from compile import compile_criterion  # noqa: E402
from extract import extract_rules  # noqa: E402
from split import split_block  # noqa: E402

CACHE = ROOT / "data" / "compiled" / "trials.pkl"


def compile_corpus(limit=None):
    """{trial_id: [Criterion]} plus {trial_id: metadata}."""
    path = ROOT / "data" / "raw" / "nsclc_trials.jsonl"
    trials = [json.loads(l) for l in path.read_text().splitlines()]
    if limit:
        trials = trials[:limit]

    compiled, meta = {}, {}
    for t in trials:
        crits = []
        for raw in split_block(t["eligibility_text"], t["nct_id"]):
            crits.extend(compile_criterion(raw))
        compiled[t["nct_id"]] = crits
        meta[t["nct_id"]] = {
            "title": t["title"],
            "phases": t.get("phases", []),
            "sponsor": t.get("sponsor"),
            "locations": t.get("locations", [])[:5],
            "eligibility_text": t["eligibility_text"],
        }
    return compiled, meta


def load_corpus(rebuild=False, limit=None):
    if CACHE.exists() and not rebuild and not limit:
        with CACHE.open("rb") as f:
            return pickle.load(f)
    data = compile_corpus(limit)
    if not limit:
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        with CACHE.open("wb") as f:
            pickle.dump(data, f)
    return data


def _span(report, needle):
    i = report.find(needle)
    return (i, i + len(needle)) if i >= 0 else None


# Defined next to the query path that depends on it. Re-exported here because
# the eval scripts and load_persona() below have always imported it from
# loader, and one regex with two definitions is one regex too many.
from service import HISTORY_COMPLETE  # noqa: E402,F401


def load_persona(name="maya_torres"):
    """Persona -> PatientRecord via the real extractor.

    The persona is its report text and nothing else. Every field is produced by
    extract_rules, so the fixture cannot drift from what the extractor actually
    does -- the failure mode this replaced, where a hand-written record asserted
    negatives the report never stated in recognisable form.
    """
    from personas import PERSONAS
    d = PERSONAS[name]
    p = extract_rules(d["report"], d["index_date"])
    p.therapy_history_complete = bool(HISTORY_COMPLETE.search(d["report"]))
    return p


if __name__ == "__main__":
    compiled, meta = load_corpus(rebuild=True)
    n = sum(len(v) for v in compiled.values())
    print(f"compiled {len(compiled)} trials, {n} criteria -> {CACHE}")
