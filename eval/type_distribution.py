"""Stage-1 command 3: criterion type distribution from 30 hand-read eligibility blocks.

Determines the build order for the predicate compiler.
"""

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "data" / "eval"))

NAMES = {
    "LAB": "LAB_THRESHOLD",
    "WASH": "WASHOUT",
    "AGE": "AGE",
    "PS": "PERFORMANCE_STATUS",
    "BIO": "BIOMARKER",
    "HIST": "HISTOLOGY",
    "STAGE": "STAGE",
    "PRIOR": "PRIOR_THERAPY",
    "COMORB": "COMORBIDITY",
    "FT": "FREE_TEXT",
}
TYPED = [k for k in NAMES if k != "FT"]


def main():
    crits = [
        json.loads(l)
        for l in (ROOT / "data" / "eval" / "handread_gold.jsonl").read_text().splitlines()
    ]
    LABELS = [c["labels"] for c in crits]

    n = len(crits)
    trials = len({c["trial"] for c in crits})

    # Per-criterion: does it carry at least one typed predicate?
    compilable = sum(1 for i in range(n) if set(LABELS[i]) != {"FT"})

    # Type frequency, counted per criterion (a criterion with 2 types counts once
    # for each). Also count predicate instances.
    type_crit = Counter()
    for i in range(n):
        for t in set(LABELS[i]):
            type_crit[t] += 1

    incl = sum(1 for c in crits if c["incl"])

    print("=" * 68)
    print("CRITERION TYPE DISTRIBUTION - 30 hand-read NSCLC eligibility blocks")
    print("=" * 68)
    print(f"trials                    : {trials}")
    print(f"criteria                  : {n}  ({n / trials:.1f} per trial)")
    print(f"inclusion / exclusion     : {incl} / {n - incl}")
    print()
    print(f"criteria with >=1 typed predicate : {compilable} / {n}"
          f"  = {100 * compilable / n:.1f}%   <- ceiling for compile rate")
    print(f"criteria that are FREE_TEXT only  : {n - compilable} / {n}"
          f"  = {100 * (n - compilable) / n:.1f}%")
    print()
    print(f"{'predicate type':<22}{'criteria':>10}{'% of all':>10}   build order")
    print("-" * 68)
    order = sorted(TYPED, key=lambda t: -type_crit[t])
    for rank, t in enumerate(order, 1):
        c = type_crit[t]
        print(f"{NAMES[t]:<22}{c:>10}{100 * c / n:>9.1f}%   {rank}")
    print("-" * 68)
    print(f"{'FREE_TEXT (only)':<22}{n - compilable:>10}"
          f"{100 * (n - compilable) / n:>9.1f}%   -> LLM")
    print()

    multi = sum(1 for i in range(n) if len(set(LABELS[i])) > 1)
    print(f"criteria needing >1 predicate type: {multi} ({100 * multi / n:.1f}%)")
    print("  -> the compiler must emit a LIST of predicates per criterion,")
    print("     not one predicate per criterion.")

    # Cumulative coverage if types are built in frequency order.
    print()
    print("cumulative criterion coverage as types are implemented in order:")
    covered = set()
    for t in order:
        covered.add(t)
        got = sum(1 for i in range(n) if set(LABELS[i]) & covered)
        print(f"  +{NAMES[t]:<20} -> {100 * got / n:5.1f}% of criteria touched")


if __name__ == "__main__":
    main()
