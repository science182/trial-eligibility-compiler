"""Retrieval recall on TREC CT 2022 — the component 9.4 does not test.

Metric 9.4 ranks TrialGPT's own candidate pool, so it compares rankers only.
This measures the retrieval arm: given a corpus and a patient note, does the
hybrid surface the eligible trials at all?

CORPUS CAVEAT, and it matters. TREC 2021/2022 ship no corpus.jsonl (only the
SIGIR split does), so the corpus here is the UNION of every trial appearing in
any patient's pool -- 11,604 trials that TrialGPT's own retrieval already
surfaced. Recall against it is therefore optimistic relative to searching the
full ~500k-trial registry, and cannot be compared to a published retrieval
number. It measures whether this retriever can re-find known-relevant trials in
a pool of 11.6k, which is a real but easier task.
"""

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "eval"))

from ranking_benchmark import load, trial_text  # noqa: E402
from retrieve import BM25, DenseLSA, order, rrf, tokenize  # noqa: E402

OUT = ROOT / "data" / "eval" / "retrieval_recall.json"
CUTOFFS = (10, 50, 100, 254, 500, 1000)


def build_corpus(topics):
    docs, index = {}, {}
    for t in topics:
        for tr, _ in t["trials"]:
            nct = tr.get("NCTID")
            if nct not in docs:
                index[nct] = len(docs)
                docs[nct] = trial_text(tr)
    return list(docs), list(docs.values()), index


def recall_at(ranked_ncts, relevant, k):
    if not relevant:
        return None
    return len(set(ranked_ncts[:k]) & relevant) / len(relevant)


def main():
    topics = load("trec_2022")
    ncts, texts, index = build_corpus(topics)
    print(f"corpus: {len(ncts)} unique trials from 50 patient pools")

    t0 = time.time()
    print("indexing BM25 ...", flush=True)
    bm = BM25([tokenize(x) for x in texts])
    print(f"  {time.time() - t0:.0f}s")
    t1 = time.time()
    print("indexing LSA (TF-IDF + truncated SVD) ...", flush=True)
    dense = DenseLSA(texts, dims=256)
    print(f"  {time.time() - t1:.0f}s")

    arms = {"BM25": [], "LSA": [], "hybrid (RRF)": []}
    latency = []

    for t in topics:
        eligible = {tr.get("NCTID") for tr, lab in t["trials"] if lab == 2}
        if not eligible:
            continue
        q0 = time.time()
        lex_order = order(bm.scores(t["note"]))
        den_order = order(dense.scores(t["note"]))
        fused = rrf([lex_order, den_order])
        latency.append(time.time() - q0)

        for name, idxs in (("BM25", lex_order), ("LSA", den_order),
                           ("hybrid (RRF)", fused)):
            row = {k: recall_at([ncts[i] for i in idxs], eligible, k)
                   for k in CUTOFFS}
            arms[name].append(row)

    print("\n" + "=" * 62)
    print("RETRIEVAL RECALL of ELIGIBLE trials (qrels label 2)")
    print("=" * 62)
    head = f"{'system':<16}" + "".join(f"{'R@' + str(k):>8}" for k in CUTOFFS)
    print(head)
    print("-" * len(head))
    results = {}
    for name, rows in arms.items():
        avg = {k: sum(r[k] for r in rows) / len(rows) for k in CUTOFFS}
        results[name] = avg
        print(f"{name:<16}" + "".join(f"{avg[k]:>8.3f}" for k in CUTOFFS))
    print("-" * len(head))
    print(f"\nqueries: {len(arms['BM25'])}   "
          f"mean retrieval latency: {sum(latency) / len(latency) * 1000:.0f} ms   "
          f"0 model calls")
    print("\nCorpus is the union of TrialGPT's per-patient pools (11.6k trials),")
    print("not the full registry, so these are optimistic and are NOT")
    print("comparable to a published retrieval figure.")

    OUT.write_text(json.dumps(results, indent=1) + "\n")
    print(f"\n-> {OUT}")


if __name__ == "__main__":
    main()
