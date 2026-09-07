"""Metric 9.1: compile rate over the 500-trial NSCLC corpus.

Re-run after every predicate type is added. Reports overall rate plus a
per-type breakdown, and (when the hand-read labels cover the criterion) recall
and precision against those labels for the types implemented so far.
"""

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "data" / "eval"))

from compile import compile_criterion  # noqa: E402
from split import split_block  # noqa: E402

IMPLEMENTED = {                     # grows as stage 2 proceeds
    "LAB_THRESHOLD": "LAB",
    "WASHOUT": "WASH",
    "AGE": "AGE",
    "PERFORMANCE_STATUS": "PS",
    "HISTOLOGY": "HIST",
    "STAGE": "STAGE",
    "BIOMARKER": "BIO",
    "PRIOR_THERAPY": "PRIOR",
    "COMORBIDITY": "COMORB",
}


def main():
    trials = [
        json.loads(l)
        for l in (ROOT / "data" / "raw" / "nsclc_trials.jsonl").read_text().splitlines()
    ]

    n_crit = 0
    compiled_crit = 0
    type_counts = Counter()      # predicates emitted, by type
    crit_with_type = Counter()   # criteria touching each type
    per_trial = []

    for t in trials:
        raws = split_block(t["eligibility_text"], t["nct_id"])
        hit = 0
        for raw in raws:
            n_crit += 1
            preds = compile_criterion(raw)
            types = {p.predicate_type for p in preds}
            for ty in types:
                crit_with_type[ty] += 1
            for p in preds:
                type_counts[p.predicate_type] += 1
            if types != {"FREE_TEXT"}:
                compiled_crit += 1
                hit += 1
        per_trial.append((t["nct_id"], len(raws), hit))

    print("=" * 66)
    print("COMPILE RATE  (9.1)   corpus: 500 recruiting NSCLC trials")
    print("=" * 66)
    print(f"criteria total            : {n_crit:,}")
    print(f"criteria compiled         : {compiled_crit:,}"
          f"  = {100 * compiled_crit / n_crit:.1f}%")
    print(f"criteria -> FREE_TEXT     : {n_crit - compiled_crit:,}"
          f"  = {100 * (n_crit - compiled_crit) / n_crit:.1f}%")
    print()
    print(f"{'predicate type':<22}{'criteria':>10}{'predicates':>12}{'% crit':>9}")
    print("-" * 66)
    for ty, c in type_counts.most_common():
        print(f"{ty:<22}{crit_with_type[ty]:>10}{c:>12}"
              f"{100 * crit_with_type[ty] / n_crit:>8.1f}%")
    print()

    trials_with = sum(1 for _, _, h in per_trial if h)
    print(f"trials with >=1 compiled criterion: {trials_with}/{len(trials)}"
          f" = {100 * trials_with / len(trials):.0f}%")

    _score_against_handread()


def _score_against_handread():
    """Precision/recall on the hand-read gold set, for implemented types only.

    The gold set is keyed by criterion text (see eval/migrate_gold.py), so a
    splitter change cannot silently misalign labels -- it surfaces as
    unlabelled criteria instead.
    """
    path = ROOT / "data" / "eval" / "handread_gold.jsonl"
    if not path.exists():
        print("\n(no gold set; run eval/migrate_gold.py)")
        return
    crits = [json.loads(l) for l in path.read_text().splitlines()]

    print()
    print("-" * 66)
    print(f"against {len(crits)} hand-read criteria (implemented types only)")
    print("-" * 66)

    class R:
        def __init__(self, c):
            self.trial_id = c["trial"]
            self.raw_text = c["text"]
            self.is_inclusion = c["incl"]
            self.start = self.end = 0
            self.context = ()
            self.polarity_flipped = c.get('flipped', False)

    for ty, code in IMPLEMENTED.items():
        tp = fp = fn = 0
        misses, spurious = [], []
        for c in crits:
            gold = code in c["labels"]
            got = any(p.predicate_type == ty for p in compile_criterion(R(c)))
            if gold and got:
                tp += 1
            elif gold and not got:
                fn += 1
                misses.append(c["text"])
            elif got and not gold:
                fp += 1
                spurious.append(c["text"])
        prec = tp / (tp + fp) if tp + fp else 0.0
        rec = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
        print(f"{ty}:  precision {prec:.3f}   recall {rec:.3f}   F1 {f1:.3f}"
              f"   (tp={tp} fp={fp} fn={fn})")
        for label, items in (("MISSED", misses), ("SPURIOUS", spurious)):
            for x in items[:4]:
                print(f"   {label:<9}{x[:88]}")


if __name__ == "__main__":
    main()
