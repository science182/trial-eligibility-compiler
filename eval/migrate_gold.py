"""Rebuild the hand-read gold set after a splitter change.

The original gold set was keyed by position in the split output, so changing
the splitter silently invalidated it. The gold set is now keyed by criterion
TEXT: labels carry over wherever the text is unchanged, and anything genuinely
new is reported for hand labelling instead of being quietly dropped.

Run after any change to split.py. Exits non-zero if unlabelled criteria remain.
"""

import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "data" / "eval"))

from split import split_block  # noqa: E402

GOLD = ROOT / "data" / "eval" / "handread_gold.jsonl"

# Criteria formed by the splitter rewrite (continuations rejoined, headers
# absorbed), hand-read 2026-08-14. Keyed by a distinctive prefix.
NEW_LABELS = {
    "Absolute neutrophil count at least 1.5": ["LAB"],
    "Absolute neutrophil count ≥ 1.5 x 109/L , Platelets": ["LAB"],
    "Alanine aminotransferase (ALT) and aspartate aminotransferase (AST) ≤ 3.0": ["LAB"],
    "Bilirubin ≤ 1.5 × the upper limit of normal (ULN). For subjects": ["LAB"],
    "Concurrent uncontrolled hypertension defined as sustained BP": ["LAB", "COMORB"],
    "Creatinine ≤ 1.5 × ULN, and creatinine clearance": ["LAB"],
    "Creatinine≤ 1.5 x institutional upper limit of normal ,if not": ["LAB"],
    "Documented radiographic progression observed in at least 3": ["PRIOR"],
    "Has any of the following cardiac diagnoses": ["COMORB", "LAB", "WASH"],
    "International normalized ratio (INR) and prothrombin time": ["LAB"],
    "Known EGFR mutations or ALK translocations. For non-squamous": ["BIO"],
    "Known uncontrolled symptomatic brain metastases or cranial": ["COMORB", "WASH"],
    "Laboratory findings must confirm adequate bone marrow function": ["LAB"],
    "Measurable disease per RECIST v1.1 with at least 1 thoracic": ["FT"],
    "NTRK fusion iii. MET overexpression": ["BIO"],
    "Serum creatinine ≤ 1.5 × ULN or creatinine clearance (CrCl) ≥ 30": ["LAB"],
    "Total bilirubin no more than 1.5 × the upper limit of normal": ["LAB"],
    "Total bilirubin ≤ 1.5 x upper limit of normal (ULN) for the institution": ["LAB"],
}


def load_prior_labels():
    """text -> labels, from the current gold file or the original indexed one."""
    if GOLD.exists():
        return {
            r["text"]: r["labels"]
            for r in map(json.loads, GOLD.read_text().splitlines())
        }
    from handread_labels import LABELS
    old = [
        json.loads(l)
        for l in (ROOT / "data" / "eval" / "handread_30.jsonl").read_text().splitlines()
    ]
    return {c["text"]: LABELS[c["idx"]] for c in old}


def main():
    trials = [
        json.loads(l)
        for l in (ROOT / "data" / "raw" / "nsclc_trials.jsonl").read_text().splitlines()
    ]
    random.seed(42)
    sample = random.sample(trials, 30)

    prior = load_prior_labels()
    rows, unlabelled = [], []
    carried = added = 0

    for t in sample:
        for c in split_block(t["eligibility_text"], t["nct_id"]):
            labels = prior.get(c.raw_text)
            if labels:
                carried += 1
            else:
                labels = next(
                    (v for k, v in NEW_LABELS.items() if c.raw_text.startswith(k)),
                    None,
                )
                if labels:
                    added += 1
                else:
                    unlabelled.append(c.raw_text)
                    continue
            rows.append({
                "trial": c.trial_id,
                "incl": c.is_inclusion,
                "flipped": c.polarity_flipped,
                "text": c.raw_text,
                "labels": labels,
            })

    print(f"criteria in sample : {carried + added + len(unlabelled)}")
    print(f"  labels carried   : {carried}")
    print(f"  newly labelled   : {added}")
    print(f"  UNLABELLED       : {len(unlabelled)}")
    for x in unlabelled:
        print(f"    {x[:110]}")

    if unlabelled:
        print("\nAdd these to NEW_LABELS and re-run. Gold file NOT written.")
        return 1

    with GOLD.open("w") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"\nwrote {len(rows)} labelled criteria -> {GOLD}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
