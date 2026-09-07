"""Human-readable names for the internal vocabulary.

Every verdict the interface shows is a sentence, and until this module existed
those sentences leaked the code's own enums: "histology ADENOCARCINOMA matches
SOLID_TUMOR", "BILIRUBIN 0.7 mg/dL", "4 weeks washout from 2026-07-28". A
coordinator reads that as a machine talking to itself.

The rule is narrow: a token that a clinician would genuinely write in capitals
stays in capitals, everything else becomes ordinary words. Getting that
backwards in either direction is worse than not translating at all -- "Nsclc"
and "creatinine_clearance" are both wrong.

One module rather than a helper per evaluator, because the same analyte name
appears in a lab reason, a missing-data row and a provenance key, and they have
to agree.
"""

import re

# Written in capitals on a real pathology or chemistry report.
ABBREV = {
    # disease / histology
    "NSCLC", "SCLC", "LCNEC", "LUSC", "LUAD",
    # performance and cardiac
    "ECOG", "KPS", "LVEF", "QTC", "QTCF", "QTCB", "NYHA", "MUGA", "ECG",
    # chemistry and haematology
    "ANC", "WBC", "RBC", "AST", "ALT", "ALP", "LDH", "GGT", "INR", "APTT",
    "PT", "PTT", "BUN", "CRP", "ESR", "HBA1C", "TSH", "FT4", "GFR", "EGFR",
    "ULN", "LLN",
    # infectious and organ systems
    "HIV", "HBV", "HCV", "TB", "CNS", "GI", "ILD", "COPD", "CHF", "MI", "DVT",
    "PE", "COVID", "COVID-19",
    # biomarker scoring
    "TPS", "CPS", "TMB", "MSI", "IHC", "FISH", "NGS", "VAF", "PD-L1",
}

# Tokens whose canonical spelling is not just a case change.
SPECIAL = {
    "QTC": "QTc",
    "QTCF": "QTcF",
    "QTCB": "QTcB",
    "PD_L1": "PD-L1",
    "HBA1C": "HbA1c",
    "COVID_19": "COVID-19",
    "NON_SMALL_CELL": "non-small cell",
    "SOLID_TUMOR": "solid tumor",
    "NSCLC_SQUAMOUS": "squamous NSCLC",
    "NSCLC_NONSQUAMOUS": "non-squamous NSCLC",
    "CREATININE_CLEARANCE": "creatinine clearance",
    "TOTAL_BILIRUBIN": "total bilirubin",
    "PRIOR_MALIGNANCY": "prior malignancy",
    "SECOND_MALIGNANCY": "second malignancy",
    "BRAIN_METASTASES": "brain metastases",
    "LIVER_METASTASES": "liver metastases",
    "BONE_METASTASES": "bone metastases",
    "LEPTOMENINGEAL": "leptomeningeal disease",
    "GI_IMPAIRMENT": "GI impairment",
    "INFECTION_HOSPITALIZATION": "hospitalization for infection",
    "ANTICANCER_THERAPY": "anticancer therapy",
    "CHECKPOINT_INHIBITOR": "checkpoint inhibitor",
    "MONOCLONAL_ANTIBODY": "monoclonal antibody",
    "EGFR_TKI": "EGFR TKI",
    "ANY": "therapy of any kind",
}

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def term(name):
    """An internal token as a clinician would write it mid-sentence."""
    if name is None:
        return ""
    raw = str(name).strip()
    if not raw:
        return ""
    key = raw.upper().replace(" ", "_")
    if key in SPECIAL:
        return SPECIAL[key]
    if key in ABBREV:
        return key
    # Mixed vocabulary: keep any part that is a real abbreviation.
    parts = key.split("_")
    if len(parts) > 1:
        return " ".join(
            SPECIAL.get(p, p if p in ABBREV else p.lower()) for p in parts)
    # A bare token that is already mixed case came from source text, not an
    # enum -- leave it exactly as written.
    return raw if raw != key else raw.lower()


def sentence(name):
    """Like term(), but fit to start a sentence: 'Bilirubin', not 'bilirubin'."""
    t = term(name)
    if not t:
        return ""
    first = t.split(" ", 1)[0]
    if first.upper() in ABBREV or first in SPECIAL.values():
        return t
    return t[0].upper() + t[1:]


def human_date(d):
    """date or ISO string -> '28 Jul 2026'. Anything else passes through."""
    if d is None:
        return ""
    if hasattr(d, "year") and hasattr(d, "month"):
        return f"{d.day} {MONTHS[d.month - 1]} {d.year}"
    s = str(d)
    if _ISO.match(s):
        y, m, day = (int(x) for x in s.split("-"))
        return f"{day} {MONTHS[m - 1]} {y}"
    return s
