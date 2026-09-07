"""Emit the deck's live figures as JSON, straight from the running system.

    python3 deck/figures.py        ->  deck/figures.json

Every number and date the deck asserts is produced here by running the real
pipeline, so the slides cannot drift from the product. Transcribed figures rot:
the deck said a trial opened "25 Aug 2026" for three weeks after that day had
passed, which is the same failure the app had before its fixture was rebased.

Dates are rebased to today, exactly as the served demo is, so a deck rebuilt on
any day states dates that are still in the future. The intervals -- 11 days and
25 days -- are invariant, because all of the arithmetic is relative.

`build.js` refuses to run without this file rather than falling back to stale
literals.
"""

import json
import sys
from collections import Counter
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "data" / "eval"))

from loader import load_corpus                      # noqa: E402
from personas import MAYA_TORRES                    # noqa: E402
from service import (CORPUS_SNAPSHOT, assess_payload,  # noqa: E402
                     rebase_persona)

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def human(iso):
    y, m, d = (int(x) for x in iso.split("-"))
    return f"{d} {MONTHS[m - 1]} {y}"


def main():
    compiled, meta = load_corpus()
    persona = rebase_persona(MAYA_TORRES)
    out = assess_payload(compiled, meta, persona["report"], persona["index_date"])

    idx = date.fromisoformat(out["patient"]["index_date"])
    counts = Counter(t["state"] for t in out["trials"])

    dated = sorted((t for t in out["trials"] if t["eligible_date"]),
                   key=lambda t: t["eligible_date"])
    for t in dated:
        assert date.fromisoformat(t["eligible_date"]) > idx, \
            f"{t['id']} opens in the past — the deck must never say that"

    blocked = next(t for t in out["trials"] if t["id"] == "NCT06357533")
    washout = next(r for t in dated[:1] for r in t["rows"]
                   if r["verdict"] == "pending")

    figures = {
        "generated": date.today().isoformat(),
        "index_date": idx.isoformat(),
        "index_human": human(idx.isoformat()),
        "counts": {
            "eligible_now": counts["eligible_now"],
            "eligible_on_date": counts["eligible_on_date"],
            "undetermined": counts["undetermined"],
            "blocked": counts["blocked"],
        },
        "dated": [
            {"id": t["id"],
             "date": t["eligible_date"],
             "human": human(t["eligible_date"]),
             "short": human(t["eligible_date"]).rsplit(" ", 1)[0],
             "days": (date.fromisoformat(t["eligible_date"]) - idx).days}
            for t in dated
        ],
        "washout": {
            "trial": dated[0]["id"],
            "reason": washout["reason"],
            "anchor": washout["anchor_date"],
            "anchor_human": human(washout["anchor_date"]),
            "opens_human": human(dated[0]["eligible_date"]),
        },
        "blocked_example": {"id": blocked["id"],
                            "reason": blocked["blocking_reason"]},
        "missing": out["missing_headline"],
        "timing": {"trials": out["timing"]["trials"],
                   "model_calls": out["timing"]["model_calls"]},
        "source": out["source"],
        "snapshot_human": human(CORPUS_SNAPSHOT),
    }

    path = Path(__file__).parent / "figures.json"
    path.write_text(json.dumps(figures, indent=2) + "\n")
    d = figures["dated"]
    print(f"wrote {path.name}")
    print(f"  index date  {figures['index_human']}")
    print(f"  counts      {figures['counts']}")
    print(f"  dated       " +
          ", ".join(f"{x['human']} (+{x['days']}d)" for x in d))
    print(f"  snapshot    {figures['snapshot_human']}")


if __name__ == "__main__":
    main()
