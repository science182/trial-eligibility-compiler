"""Download and verify the TrialGPT cached TREC corpus files.

This is the Stage-1 gate from the build spec: if these files do not download
or parse, the 9.4 ranking benchmark is closed and the deck stands on 9.1/9.2.

Note: ncbi-nlp/TrialGPT ships corpus.jsonl only for the SIGIR split. For TREC
2021/2022 it ships retrieved_trials.json, which is the cached candidate pool
(query -> ranked corpus of trials with their eligibility text) plus qrels.
"""

import json
import urllib.request
from pathlib import Path

BASE = "https://raw.githubusercontent.com/ncbi-nlp/TrialGPT/main/"
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "raw" / "trialgpt"

FILES = [
    "dataset/trec_2021/retrieved_trials.json",
    "dataset/trec_2021/queries.jsonl",
    "dataset/trec_2021/qrels/test.tsv",
    "dataset/trec_2022/retrieved_trials.json",
    "dataset/trec_2022/queries.jsonl",
    "dataset/trec_2022/qrels/test.tsv",
]


def download():
    for rel in FILES:
        dest = OUT / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists() and dest.stat().st_size > 0:
            print(f"  cached  {rel}  ({dest.stat().st_size:,} bytes)")
            continue
        print(f"  getting {rel} ...", flush=True)
        urllib.request.urlretrieve(BASE + rel, dest)
        print(f"          -> {dest.stat().st_size:,} bytes")


def verify():
    ok = True
    for split in ("trec_2021", "trec_2022"):
        print(f"\n--- {split} ---")
        d = OUT / "dataset" / split
        try:
            rt = json.loads((d / "retrieved_trials.json").read_text())
        except Exception as e:  # noqa: BLE001
            print(f"  FAIL retrieved_trials.json did not parse: {e}")
            ok = False
            continue

        n_trials = sum(
            len(v) for entry in rt for k, v in entry.items() if k.isdigit()
        )
        print(f"  patients (queries)        : {len(rt)}")
        print(f"  candidate trials (total)  : {n_trials:,}")
        print(f"  avg candidates / patient  : {n_trials / max(len(rt), 1):.0f}")

        # structure probe on one trial
        first = None
        for entry in rt:
            for k, v in entry.items():
                if k.isdigit() and v:
                    first = v[0]
                    break
            if first:
                break
        if first:
            print(f"  trial keys                : {sorted(first.keys())}")
            elig = first.get("inclusion_criteria", "") + first.get(
                "exclusion_criteria", ""
            )
            print(f"  sample NCT                : {first.get('NCTID')}")
            print(f"  sample eligibility chars  : {len(elig)}")

        qrels = (d / "qrels" / "test.tsv").read_text().strip().split("\n")
        print(f"  qrels rows                : {len(qrels):,}")
        print(f"  qrels sample              : {qrels[0]!r}")

        queries = [json.loads(x) for x in (d / "queries.jsonl").read_text().strip().split("\n")]
        print(f"  queries                   : {len(queries)}")
        print(f"  query keys                : {sorted(queries[0].keys())}")
    return ok


if __name__ == "__main__":
    print("Downloading TrialGPT cached TREC files...")
    download()
    print("\nVerifying parse...")
    good = verify()
    print("\nGATE:", "PASS - benchmark 9.4 is open" if good else "FAIL - drop 9.4")
