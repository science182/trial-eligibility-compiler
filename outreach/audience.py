"""Who actually screens patients for these trials -- from the corpus itself.

The audience question has a data answer sitting in `data/raw/nsclc_trials.jsonl`
already. Every recruiting trial lists the sites running it, so counting sites
across 500 trials ranks the places where somebody's job is screening lung
cancer patients against eligibility criteria this week.

    python3 outreach/audience.py            # top institutions and metros
    python3 outreach/audience.py --csv out.csv

Deliberately institution-level. ClinicalTrials.gov publishes a named contact
person for most trials; that person's address is there so patients and referring
physicians can ask about *that trial*, and using it to market a tool is a misuse
of it however good the tool is. Nothing personal is fetched, parsed or written
here -- see AUDIENCE.md for what to do with the list instead.
"""

import argparse
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "nsclc_trials.jsonl"

# A site is listed under whatever string the sponsor typed, so the same cancer
# centre appears as several. Collapsing to the parent organisation is the whole
# point of the ranking: one coordinating office, not seven branch spellings.
SYSTEM = [
    (r"\bMD Anderson\b", "MD Anderson Cancer Center"),
    (r"\bMayo Clinic\b", "Mayo Clinic"),
    (r"\bMemorial Sloan.?Kettering\b|\bMSKCC\b", "Memorial Sloan Kettering"),
    (r"\bDana.?Farber\b", "Dana-Farber Cancer Institute"),
    (r"\bCleveland Clinic\b", "Cleveland Clinic"),
    (r"\bJohns Hopkins\b", "Johns Hopkins"),
    (r"\bMassachusetts General\b|\bMass General\b|\bBrigham and Women\b",
     "Mass General Brigham"),
    (r"\bStanford\b", "Stanford Medicine"),
    (r"\bUCLA\b|University of California,? Los Angeles", "UCLA Health"),
    (r"\bUCSF\b|University of California,? San Francisco", "UCSF"),
    (r"\bUC Davis\b|University of California,? Davis", "UC Davis Health"),
    (r"\bUC Irvine\b|University of California,? Irvine", "UC Irvine Health"),
    (r"\bUniversity of California,? San Diego\b|\bUCSD\b|Moores Cancer",
     "UC San Diego Health"),
    (r"\bNorthwestern\b", "Northwestern Medicine"),
    (r"\bMount Sinai\b", "Mount Sinai"),
    (r"\bNYU\b|New York University", "NYU Langone"),
    (r"\bColumbia University\b|\bNewYork-Presbyterian\b", "Columbia / NY-Presbyterian"),
    (r"\bWeill Cornell\b", "Weill Cornell"),
    (r"\bRoswell Park\b", "Roswell Park"),
    (r"\bFox Chase\b", "Fox Chase Cancer Center"),
    (r"\bMoffitt\b", "Moffitt Cancer Center"),
    (r"\bFlorida Cancer Specialists\b", "Florida Cancer Specialists"),
    (r"\bSarah Cannon\b", "Sarah Cannon Research Institute"),
    (r"\bNEXT Oncology\b|\bNext Oncology\b", "NEXT Oncology"),
    (r"\bUniversity of Michigan\b|\bRogel\b", "University of Michigan Rogel"),
    (r"\bWashington University\b|\bSiteman\b", "Washington University / Siteman"),
    (r"\bVanderbilt\b", "Vanderbilt-Ingram"),
    (r"\bEmory\b|\bWinship\b", "Emory Winship"),
    (r"\bDuke\b", "Duke Cancer Institute"),
    (r"\bUniversity of Colorado\b", "University of Colorado"),
    (r"\bOHSU\b|Oregon Health", "OHSU Knight"),
    (r"\bFred Hutch\b|Seattle Cancer Care", "Fred Hutchinson"),
    (r"\bUniversity of Chicago\b", "University of Chicago"),
    (r"\bUniversity of Pennsylvania\b|\bAbramson\b|\bPenn Medicine\b",
     "Penn Medicine / Abramson"),
    (r"\bYale\b|\bSmilow\b", "Yale Cancer Center"),
    (r"\bCity of Hope\b", "City of Hope"),
    (r"\bUT Southwestern\b", "UT Southwestern"),
    (r"\bOhio State\b|\bJames Cancer\b", "Ohio State James"),
    (r"\bUniversity of Texas\b(?!.*Anderson)", "University of Texas (other)"),
    (r"\bMassive Bio\b", "Massive Bio"),
    (r"\bHonorHealth\b", "HonorHealth"),
    (r"\bSCRI\b", "Sarah Cannon Research Institute"),
    (r"\bTennessee Oncology\b", "Tennessee Oncology"),
    (r"\bUniversity of Wisconsin\b|\bCarbone\b", "UW Carbone"),
    (r"\bHackensack\b|\bJohn Theurer\b", "Hackensack Meridian"),
    (r"\bBeth Israel\b", "Beth Israel"),
    (r"\bUniversity of Alabama\b|\bUAB\b|\bO'?Neal\b", "UAB O'Neal"),
]
SYSTEM = [(re.compile(p, re.I), name) for p, name in SYSTEM]

# A trailing branch or department, which is the same organisation for our
# purposes: "- Sarasota", "(Site 0123)", ", Department of Oncology".
TRIM = re.compile(r"\s*[-–—(,/]\s*(site\s*\d+|dept\.?|department|div\.?|division)?.*$",
                  re.I)


def organisation(facility):
    for pat, name in SYSTEM:
        if pat.search(facility):
            return name
    short = TRIM.sub("", facility).strip(" .,-")
    return short or facility


def load():
    if not RAW.exists():
        sys.exit(f"missing {RAW.relative_to(ROOT)} -- run the fetch step first")
    with RAW.open() as f:
        return [json.loads(line) for line in f if line.strip()]


def rank(trials):
    """Trials per organisation, and the metros they sit in."""
    org_trials = defaultdict(set)
    org_country = defaultdict(Counter)
    org_city = defaultdict(Counter)
    metro = defaultdict(set)

    for t in trials:
        for loc in t.get("locations") or []:
            fac = (loc.get("facility") or "").strip()
            if not fac:
                continue
            org = organisation(fac)
            org_trials[org].add(t["nct_id"])
            country = (loc.get("country") or "?").strip()
            org_country[org][country] += 1
            city = ", ".join(x for x in ((loc.get("city") or "").strip(),
                                         (loc.get("state") or "").strip() or country)
                             if x)
            org_city[org][city] += 1
            if city:
                metro[city].add(t["nct_id"])

    rows = [{
        "organisation": org,
        "trials": len(ids),
        "country": org_country[org].most_common(1)[0][0],
        "main_site": org_city[org].most_common(1)[0][0],
        "sites": sum(org_city[org].values()),
    } for org, ids in org_trials.items()]
    rows.sort(key=lambda r: (-r["trials"], r["organisation"]))

    metros = sorted(((c, len(ids)) for c, ids in metro.items()),
                    key=lambda kv: -kv[1])
    return rows, metros


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--top", type=int, default=25)
    ap.add_argument("--csv", help="write the full ranking to this file")
    a = ap.parse_args()

    trials = load()
    rows, metros = rank(trials)
    sited = sum(1 for t in trials if t.get("locations"))

    print(f"\n{len(trials)} recruiting NSCLC trials, {sited} with a named site, "
          f"{len(rows)} distinct organisations\n")

    print(f"  {'trials':>6}  {'sites':>5}  organisation")
    print(f"  {'-'*6}  {'-'*5}  {'-'*54}")
    for r in rows[:a.top]:
        print(f"  {r['trials']:>6}  {r['sites']:>5}  {r['organisation'][:44]:<44} "
              f"{r['main_site'][:24]}")

    print(f"\n  top metros by trials running there\n")
    for city, n in metros[:12]:
        print(f"  {n:>6}  {city}")

    # The tail is the honest part of this: how concentrated the audience is
    # determines whether outreach is 20 conversations or 2,000.
    tot = sum(r["trials"] for r in rows)
    top20 = sum(r["trials"] for r in rows[:20])
    print(f"\n  concentration: the top 20 organisations account for "
          f"{top20 / tot:.0%} of site-trial pairs")
    one = sum(1 for r in rows if r["trials"] == 1)
    print(f"  {one} of {len(rows)} organisations run exactly one of these trials")

    if a.csv:
        with open(a.csv, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
        print(f"\n  wrote {len(rows)} rows to {a.csv}")


if __name__ == "__main__":
    main()
