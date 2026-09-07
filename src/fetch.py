"""ClinicalTrials.gov v2 API client. Cached to disk, rate limited.

Pulls recruiting interventional NSCLC trials. Writes one JSON dump to
data/raw/ plus a flattened JSONL of the fields the compiler needs.
"""

import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://clinicaltrials.gov/api/v2/studies"
ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"

FIELDS = [
    "NCTId",
    "BriefTitle",
    "OverallStatus",
    "StudyType",
    "Phase",
    "Condition",
    "EligibilityCriteria",
    "HealthyVolunteers",
    "Sex",
    "MinimumAge",
    "MaximumAge",
    "LocationFacility",
    "LocationCity",
    "LocationState",
    "LocationZip",
    "LocationCountry",
    "LeadSponsorName",
]


def _get(params, retries=4):
    url = API + "?" + urllib.parse.urlencode(params)
    delay = 1.0
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "trialcompiler/0.1 (research)"}
            )
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read().decode())
        except Exception as e:  # noqa: BLE001 - retry on any transport error
            if attempt == retries - 1:
                raise
            print(f"  retry {attempt + 1} after {e}")
            time.sleep(delay)
            delay *= 2
    raise RuntimeError("unreachable")


def fetch(target=500, page_size=100):
    """Fetch `target` recruiting interventional NSCLC studies."""
    studies, token = [], None
    while len(studies) < target:
        params = {
            "query.cond": "non-small cell lung cancer",
            "filter.overallStatus": "RECRUITING",
            "filter.advanced": "AREA[StudyType]INTERVENTIONAL",
            "fields": "|".join(FIELDS),
            "pageSize": min(page_size, target - len(studies)),
            "countTotal": "true",
        }
        if token:
            params["pageToken"] = token
        data = _get(params)
        batch = data.get("studies", [])
        if not batch:
            break
        studies.extend(batch)
        print(f"  fetched {len(studies)} / {target}"
              + (f"  (total available {data['totalCount']})" if "totalCount" in data else ""))
        token = data.get("nextPageToken")
        if not token:
            break
        time.sleep(0.4)  # be polite
    return studies[:target]


def flatten(s):
    """Pull the handful of fields downstream stages need out of the v2 nesting."""
    p = s.get("protocolSection", {})
    ident = p.get("identificationModule", {})
    status = p.get("statusModule", {})
    design = p.get("designModule", {})
    elig = p.get("eligibilityModule", {})
    cond = p.get("conditionsModule", {})
    loc = p.get("contactsLocationsModule", {})
    spon = p.get("sponsorCollaboratorsModule", {})

    return {
        "nct_id": ident.get("nctId"),
        "title": ident.get("briefTitle"),
        "status": status.get("overallStatus"),
        "study_type": design.get("studyType"),
        "phases": design.get("phases", []),
        "conditions": cond.get("conditions", []),
        "sponsor": spon.get("leadSponsor", {}).get("name"),
        "eligibility_text": elig.get("eligibilityCriteria", ""),
        "healthy_volunteers": elig.get("healthyVolunteers"),
        "sex": elig.get("sex"),
        "min_age": elig.get("minimumAge"),
        "max_age": elig.get("maximumAge"),
        "locations": [
            {
                "facility": x.get("facility"),
                "city": x.get("city"),
                "state": x.get("state"),
                "zip": x.get("zip"),
                "country": x.get("country"),
            }
            for x in loc.get("locations", [])
        ],
    }


def main():
    RAW.mkdir(parents=True, exist_ok=True)
    print("Fetching recruiting interventional NSCLC trials from ClinicalTrials.gov v2...")
    studies = fetch(500)

    (RAW / "nsclc_raw.json").write_text(json.dumps(studies, indent=1))

    flat = [flatten(s) for s in studies]
    with (RAW / "nsclc_trials.jsonl").open("w") as f:
        for t in flat:
            f.write(json.dumps(t) + "\n")

    with_elig = [t for t in flat if t["eligibility_text"].strip()]
    chars = [len(t["eligibility_text"]) for t in with_elig]
    print()
    print(f"trials fetched          : {len(flat)}")
    print(f"with eligibility text   : {len(with_elig)}")
    print(f"median eligibility chars: {sorted(chars)[len(chars) // 2] if chars else 0}")
    print(f"written to              : {RAW}")


if __name__ == "__main__":
    main()
