"""Metric 9.4 — NDCG@10 and Precision@10 on TREC Clinical Trials 2022.

READ THE CAVEATS BEFORE QUOTING ANY NUMBER FROM THIS FILE.

The comparison target is TrialGPT's published NDCG@10 0.7252 and P@10 0.6724.
The build spec calls 9.4 optional and says not to lead with it, which is right:

1. DIFFERENT SYSTEM CLASS. TrialGPT reranks with an LLM at criterion level.
   This ranks with zero model calls. A gap in either direction is expected.
2. GAIN CONVENTION IS UNVERIFIED. TREC relevance here is graded 0/1/2 and NDCG
   changes materially with linear vs exponential gain. Both are reported below
   because the published figure's convention could not be confirmed from the
   data shipped in the repo.
3. THE POOL IS THEIRS. Ranking runs over TrialGPT's own retrieved candidate
   set, so only the RANKER is compared, not retrieval. Our retrieval is
   measured separately as recall against that pool.
4. SYNTHETIC, NON-ONCOLOGY TOPICS. TREC patient notes are short synthetic
   admission notes across all of medicine. This system's vocabulary was built
   for NSCLC, so out-of-domain terms simply will not compile.

WHAT THE LABELS MEAN, and why the design follows from them:
    2 = patient is ELIGIBLE for the trial
    1 = trial is topically relevant but the patient is EXCLUDED
    0 = not relevant
So separating 0 from {1,2} is a topical-retrieval problem, and separating 2
from 1 is an eligibility problem. BM25 does the first; compiled predicates do
the second. That split is the experiment.
"""

import argparse
import json
import math
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from compile import compile_criterion  # noqa: E402
from evaluate import Verdict, evaluate_criterion  # noqa: E402
from extract import extract_rules  # noqa: E402
from retrieve import BM25, tokenize  # noqa: E402
from split import RawCriterion, split_block  # noqa: E402

DATA = ROOT / "data" / "raw" / "trialgpt" / "dataset"
OUT = ROOT / "data" / "eval" / "ranking_9_4.json"

PUBLISHED = {"ndcg@10": 0.7252, "p@10": 0.6724}   # TrialGPT, TREC CT 2022


# ─────────────────────────────────────────────────── data ──

def load(split="trec_2022"):
    pools = json.loads((DATA / split / "retrieved_trials.json").read_text())
    topics = []
    for entry in pools:
        trials = []
        for label in ("0", "1", "2"):
            for t in entry.get(label, []):
                trials.append((t, int(label)))
        topics.append({"id": entry["patient_id"], "note": entry["patient"],
                       "trials": trials})
    return topics


def trial_text(t):
    return " ".join(filter(None, [
        t.get("brief_title", ""), t.get("brief_summary", ""),
        " ".join(t.get("diseases_list", []) or []),
        " ".join(t.get("drugs_list", []) or []),
        t.get("inclusion_criteria", ""), t.get("exclusion_criteria", ""),
    ]))


# ───────────────────────────────────────────── structured ──

def compile_trial(t):
    """TREC ships inclusion and exclusion separately, so polarity is given."""
    crits = []
    for text, incl in ((t.get("inclusion_criteria", ""), True),
                       (t.get("exclusion_criteria", ""), False)):
        for raw in split_block(text or ""):
            raw.is_inclusion = incl
            crits.extend(c for c in compile_criterion(raw) if c.compiled)
    return crits


def structured_score(crits, patient):
    """How well the patient's known facts agree with the trial's predicates.

    Range roughly [-1, 1]. UNDETERMINED contributes nothing: an unknown fact is
    not evidence either way, which is the same abstention rule the rest of the
    system follows.
    """
    if not crits:
        return 0.0, Counter()
    groups = {}
    for c in crits:
        groups.setdefault((c.start, c.end, c.raw_text), []).append(c)

    tally = Counter()
    for g in groups.values():
        r = evaluate_criterion(g, patient)
        tally[r.verdict] += 1

    decided = tally[Verdict.MET] + tally[Verdict.NOT_MET] + tally[Verdict.PENDING]
    if not decided:
        return 0.0, tally
    # A hard failure is worth much more than a pass: one violated criterion
    # disqualifies, while one satisfied criterion says very little.
    score = (tally[Verdict.MET] - 3 * tally[Verdict.NOT_MET]
             - tally[Verdict.PENDING]) / decided
    return max(-1.0, min(1.0, score)), tally


# ──────────────────────────────────────────────── metrics ──

def dcg(gains):
    return sum(g / math.log2(i + 2) for i, g in enumerate(gains))


def ndcg_at(labels_in_rank_order, all_labels, k=10, exponential=False):
    def gain(r):
        return (2 ** r - 1) if exponential else r
    got = dcg([gain(r) for r in labels_in_rank_order[:k]])
    ideal = dcg([gain(r) for r in sorted(all_labels, reverse=True)[:k]])
    return got / ideal if ideal else 0.0


def precision_at(labels, k=10, threshold=2):
    top = labels[:k]
    return sum(1 for r in top if r >= threshold) / k if k else 0.0


# ──────────────────────────────────────────────── ranking ──

def rank_topic(topic, alpha, use_structured=True, cache=None):
    trials = topic["trials"]
    texts = [trial_text(t) for t, _ in trials]
    labels = [lab for _, lab in trials]

    bm = BM25([tokenize(x) for x in texts])
    lex = bm.scores(topic["note"])
    lo, hi = min(lex), max(lex)
    lex_n = [(s - lo) / (hi - lo) if hi > lo else 0.0 for s in lex]

    struct = [0.0] * len(trials)
    if use_structured:
        patient = extract_rules(topic["note"])
        for i, (t, _) in enumerate(trials):
            key = t.get("NCTID")
            crits = cache.get(key) if cache is not None else None
            if crits is None:
                crits = compile_trial(t)
                if cache is not None:
                    cache[key] = crits
            struct[i], _ = structured_score(crits, patient)

    final = [alpha * lex_n[i] + (1 - alpha) * ((struct[i] + 1) / 2)
             for i in range(len(trials))]
    order = sorted(range(len(trials)), key=lambda i: final[i], reverse=True)
    return [labels[i] for i in order], labels


def evaluate(topics, alpha, use_structured, cache):
    rows = []
    for t in topics:
        ranked, all_labels = rank_topic(t, alpha, use_structured, cache)
        rows.append({
            "id": t["id"], "n": len(all_labels),
            "ndcg_lin": ndcg_at(ranked, all_labels, 10, False),
            "ndcg_exp": ndcg_at(ranked, all_labels, 10, True),
            "p10_elig": precision_at(ranked, 10, 2),
            "p10_rel": precision_at(ranked, 10, 1),
        })
    n = len(rows)
    return {k: sum(r[k] for r in rows) / n
            for k in ("ndcg_lin", "ndcg_exp", "p10_elig", "p10_rel")}, rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="trec_2022")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--alpha", type=float, default=0.7,
                    help="weight on lexical vs structured")
    ap.add_argument("--sweep", action="store_true",
                    help="sweep alpha to see whether the structured arm helps")
    args = ap.parse_args()

    topics = load(args.split)
    if args.limit:
        topics = topics[:args.limit]
    pool = sum(len(t["trials"]) for t in topics)
    print(f"{args.split}: {len(topics)} topics, {pool} candidate trials "
          f"({pool / len(topics):.0f} per topic)")

    cache = {}
    t0 = time.time()
    print("\ncompiling the candidate corpus ...", flush=True)
    for t in topics:
        for tr, _ in t["trials"]:
            k = tr.get("NCTID")
            if k not in cache:
                cache[k] = compile_trial(tr)
    n_pred = sum(len(v) for v in cache.values())
    print(f"  {len(cache)} unique trials, {n_pred} predicates, "
          f"{time.time() - t0:.0f}s")

    variants = [
        ("BM25 only", 1.0, False),
        ("predicates only", 0.0, True),
        (f"hybrid (alpha={args.alpha})", args.alpha, True),
    ]
    results = {}
    for name, alpha, structured in variants:
        t1 = time.time()
        agg, rows = evaluate(topics, alpha, structured, cache)
        agg["seconds"] = round(time.time() - t1, 1)
        results[name] = agg
        print(f"  {name:<24} done in {agg['seconds']}s", flush=True)

    print("\n" + "=" * 70)
    print("METRIC 9.4  ranking on TREC Clinical Trials 2022")
    print("=" * 70)
    print(f"{'system':<26}{'NDCG@10':>10}{'NDCG@10':>10}{'P@10':>9}{'P@10':>9}")
    print(f"{'':<26}{'(linear)':>10}{'(exp)':>10}{'(elig)':>9}{'(rel)':>9}")
    print("-" * 70)
    for name, a in results.items():
        print(f"{name:<26}{a['ndcg_lin']:>10.4f}{a['ndcg_exp']:>10.4f}"
              f"{a['p10_elig']:>9.4f}{a['p10_rel']:>9.4f}")
    print("-" * 70)
    print(f"{'TrialGPT (published)':<26}{PUBLISHED['ndcg@10']:>10.4f}"
          f"{'—':>10}{PUBLISHED['p@10']:>9.4f}{'—':>9}")
    # How much does the patient record actually contain? On TREC this is the
    # whole story, so it is measured rather than asserted.
    fields = Counter()
    for t in topics:
        pr = extract_rules(t["note"])
        for name in ("age", "sex", "stage", "histology", "ecog"):
            if getattr(pr, name):
                fields[name] += 1
        fields["labs"] += len(pr.labs)
        fields["biomarkers"] += len(pr.biomarkers)
        fields["conditions"] += len(pr.comorbidities)
        fields["therapies"] += len(pr.prior_therapies)
        fields["dated therapies"] += len(pr.last_dose_dates)
    print(f"\nWhat extraction recovers from {len(topics)} TREC notes "
          f"(mean note length {sum(len(t['note']) for t in topics)//len(topics)} chars):")
    for k in ("age", "sex", "stage", "histology", "ecog", "labs", "biomarkers",
              "conditions", "therapies", "dated therapies"):
        print(f"   {k:<18}{fields[k]:>5}   ({fields[k]/len(topics):.2f} per note)")

    if args.sweep:
        print("\nalpha sweep (1.0 = lexical only, 0.0 = predicates only):")
        print(f"   {'alpha':>6}{'NDCG@10':>10}{'P@10 elig':>11}")
        for a in (1.0, 0.9, 0.8, 0.7, 0.5, 0.3, 0.0):
            agg, _ = evaluate(topics, a, a < 1.0, cache)
            print(f"   {a:>6.1f}{agg['ndcg_lin']:>10.4f}{agg['p10_elig']:>11.4f}")

    print("\nCAVEATS — do not quote a number from this table without them:")
    print("  * TrialGPT reranks with an LLM at criterion level; this uses "
          "0 model calls.")
    print("  * the published gain convention is unconfirmed, so both linear "
          "and exponential NDCG are shown.")
    print("  * ranking runs over TrialGPT's own retrieved pool, so only the "
          "ranker is compared.")
    print("  * TREC topics are synthetic, short, and span all of medicine; "
          "this compiler's vocabulary is NSCLC-specific.")

    OUT.write_text(json.dumps({"results": results, "published": PUBLISHED},
                              indent=1) + "\n")
    print(f"\n-> {OUT}")


if __name__ == "__main__":
    main()
