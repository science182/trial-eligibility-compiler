"""One-off audit: make WASH labelling in the gold set internally consistent.

Scoring WASHOUT surfaced that my own hand labels disagreed with themselves.
Of ten "prior malignancy within N years" criteria, eight carried WASH and two
did not; meanwhile several scan-recency windows had been labelled WASH.

The rule now applied throughout, and the reason for each side of it:

  WASH  <=>  the criterion states a window measured BACKWARD from a trial
             anchor, attached to a therapy, procedure, or clinical event that
             has a date on the patient record.

             This is exactly the set for which eligible_date = anchor + window
             can be computed, which is what the predicate exists to support.

  NOT WASH:
    - measurement/test/scan recency ("labs within 28 days prior to
      randomization"). The window constrains data freshness, not patient
      state; no waiting makes the patient eligible.
    - treatment DURATION ("completed 3 years adjuvant osimertinib",
      "12 weeks on continued pembrolizumab") -- not a window at all.
    - forward-looking obligations ("contraception for 6 months after the last
      dose") -- runs the other way from the anchor.
    - age, life expectancy, menopause definitions.

Idempotent: re-running after the gold file is fixed reports zero changes.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GOLD = ROOT / "data" / "eval" / "handread_gold.jsonl"

# Windowed therapies/procedures/events that were missing WASH.
ADD_WASH = [
    "Previous history of other than lung cancer is allowed if no active treatment",
    "Diagnosis of any secondary malignancy within the last 3 years",
    "Absolute neutrophil count (ANC) ≥1.5×10\\^9/L without the use of granulocyte",
    "Platelets ≥100×10\\^9/L without transfusion within the past 14 days",
    "Diagnosis of any malignancy other than non-small cell lung cancer within 5 years",
    "If they experienced disease progression within (≤) 365 days",
    "Participants must not have any grade III/IV cardiac disease",
    "Participants must not have experienced any arterial thromboembolic events",
    "Postmenopausal women with a history of abnormal vaginal bleeding within one year",
    "No disease progression in the past two weeks of signing",
    "Treatment with warfarin.",
    "History of esophageal varices, severe ulcers, unhealed wounds",
    "Any medical or psychiatric condition including recent (within the past year)",
]

# Measurement-recency windows that were wrongly marked WASH.
REMOVE_WASH = [
    "Participants must have a CT or MRI scan of the brain to evaluate",
    "No evidence of distant metastases based on FDG PET/CT scan obtained",
    "Negative pregnancy test =\\< 14 days prior to registration",
    "All relevant examinations were completed within 28 days before the operation",
]


def main():
    rows = [json.loads(l) for l in GOLD.read_text().splitlines()]
    added = removed = 0
    unmatched = []

    for prefixes, op in ((ADD_WASH, "add"), (REMOVE_WASH, "remove")):
        for pre in prefixes:
            hit = False
            for r in rows:
                if not r["text"].startswith(pre):
                    continue
                hit = True
                labels = list(r["labels"])
                if op == "add" and "WASH" not in labels:
                    labels.append("WASH")
                    added += 1
                elif op == "remove" and "WASH" in labels:
                    labels.remove("WASH")
                    if not labels:
                        labels = ["FT"]
                    removed += 1
                r["labels"] = labels
            if not hit:
                unmatched.append(pre)

    print(f"WASH added   : {added}")
    print(f"WASH removed : {removed}")
    if unmatched:
        print("PREFIX MATCHED NOTHING (gold text may have changed):")
        for u in unmatched:
            print(f"  {u[:80]}")
        return 1

    with GOLD.open("w") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    total = sum(1 for r in rows if "WASH" in r["labels"])
    print(f"criteria labelled WASH: {total} / {len(rows)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
