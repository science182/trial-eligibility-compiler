"""Analyte unit normalization.

Normalization happens at COMPILE time, never at evaluation time. By the time a
predicate reaches evaluate.py its value is already in the analyte's canonical
unit, so the evaluator only ever does a bare numeric comparison.

Two kinds of threshold appear in registry text:

  absolute   "ANC >= 1.5 x 10^9/L"        -> value in canonical unit
  ULN/LLN    "bilirubin <= 1.5 x ULN"     -> value is a MULTIPLE of the
                                             reference limit, resolved against
                                             the patient's own institutional
                                             limit at evaluation, falling back
                                             to REFERENCE_LIMITS below.

37% of lab thresholds in the NSCLC corpus are ULN-relative, so the second form
is not an edge case.
"""

import re

# ---------------------------------------------------------------- analytes

# canonical unit per analyte
CANONICAL = {
    "ANC": "10^9/L",
    "WBC": "10^9/L",
    "PLATELETS": "10^9/L",
    "LYMPHOCYTES": "10^9/L",
    "HEMOGLOBIN": "g/dL",
    "CREATININE": "mg/dL",
    "CREATININE_CLEARANCE": "mL/min",
    "BILIRUBIN": "mg/dL",
    "AST": "U/L",
    "ALT": "U/L",
    "ALP": "U/L",
    "ALBUMIN": "g/dL",
    "INR": "ratio",
    "PT": "s",
    "APTT": "s",
    "LVEF": "%",
    "QTC": "ms",
    "BP_SYSTOLIC": "mmHg",
    "BP_DIASTOLIC": "mmHg",
    "BLOOD_PRESSURE": "mmHg",
    "BMI": "kg/m^2",
}

# Longest-first alternation matters: "absolute neutrophil count" must win over
# "neutrophil", and "hemoglobin a1c" must be rejected before "hemoglobin".
ANALYTE_PATTERNS = [
    ("ANC", r"absolute\s+neutrophil\s+count|\bANC\b|neutrophil\s+count|"
            r"absolute\s+neutrophils?\s+count|\bneutrophils?\b"),
    ("PLATELETS", r"platelet\s+count|\bplatelets?\b|\bPLT\b|\bthrombocytes?\b"),
    ("HEMOGLOBIN", r"h(?:ae|e)moglobin|\bHGB\b|\bHgb\b|\bHb\b"),
    ("WBC", r"white\s+blood\s+cell\s+count|white\s+blood\s+cells?|\bWBC\b|"
            r"leu[ck]ocyte\s+count|\bleu[ck]ocytes?\b"),
    ("LYMPHOCYTES", r"lymphocyte\s+count|absolute\s+lymphocyte\s+count|"
                    r"\bALC\b|\blymphocytes?\b|\bLYM\b"),
    # clearance must be tried before plain creatinine.
    # "eGFR"/"GFR" are deliberately NOT listed: case-insensitively they match the
    # EGFR gene, which appears in nearly every NSCLC trial and would turn a
    # biomarker sentence into a renal-function threshold.
    ("CREATININE_CLEARANCE", r"creatinine\s+clearance(?:\s+rate)?|\bCrCl\b|"
                             r"\bCLcr\b|creatinine\s+CL\b|estimated\s+GFR|"
                             r"(?:estimated\s+)?glomerular\s+filtration\s+rate"),
    ("CREATININE", r"serum\s+creatinine|\bcreatinine\b|\bSCr\b|\bCr\b"),
    ("BILIRUBIN", r"total\s+bilirubin|serum\s+total\s+bilirubin|\bbilirubin\b|"
                  r"\bTBIL\b|\bTBL\b|\bT\.?\s?bili\b"),
    ("AST", r"aspartate\s+(?:amino)?transaminase|aspartate\s+aminotransferase|"
            r"\bAST\b|\bSGOT\b"),
    ("ALT", r"alanine\s+(?:amino)?transaminase|alanine\s+aminotransferase|"
            r"\bALT\b|\bSGPT\b"),
    ("ALP", r"alkaline\s+phosphatase|\bALP\b|\bALKP\b"),
    ("ALBUMIN", r"serum\s+albumin|\balbumin\b|\bALB\b"),
    ("INR", r"international\s+normali[sz]ed\s+ratio|\bINR\b"),
    ("APTT", r"activated\s+partial\s+thromboplastin\s+time|"
             r"partial\s+thromboplastin\s+time|\ba?PTT\b|\bAPTT\b"),
    ("PT", r"prothrombin\s+time|\bPT\b"),
    ("LVEF", r"left\s+ventricular\s+ejection\s+fraction|ejection\s+fraction|"
             r"\bLVEF\b"),
    ("QTC", r"\bQTcF?\b|\bQTc[BF]?\b|corrected\s+QT\s+interval|"
            r"\bQT\s+interval\s+corrected\b"),
    # Qualified forms first; the bare form is refined by the qualifier that
    # follows the number ("BP >= 150 mm Hg systolic, or >= 90 mm Hg diastolic").
    ("BP_SYSTOLIC", r"systolic\s+(?:blood\s+pressure|BP)|\bSBP\b"),
    ("BP_DIASTOLIC", r"diastolic\s+(?:blood\s+pressure|BP)|\bDBP\b"),
    ("BLOOD_PRESSURE", r"blood\s+pressure|\bBP\b"),
    ("BMI", r"body\s+mass\s+index|\bBMI\b"),
]

# Text that means the analyte name is NOT being used as that analyte.
ANALYTE_TRAPS = {
    "HEMOGLOBIN": re.compile(r"h(?:ae|e)moglobin\s*(?:a1c|a1C)|\bHbA1c\b|"
                             r"glycated|glycosylated", re.I),
    "PT": re.compile(r"\bpt\.?\s*(?:has|is|was|must|with|had)\b|patient", re.I),
}


def find_analyte(text):
    """Return (analyte, match) for the first analyte mentioned, or (None, None)."""
    best = None
    for name, pat in ANALYTE_PATTERNS:
        m = re.search(pat, text, re.I)
        if not m:
            continue
        trap = ANALYTE_TRAPS.get(name)
        if trap and trap.search(text):
            continue
        if best is None or m.start() < best[1].start():
            best = (name, m)
    return best if best else (None, None)


# ------------------------------------------------------------------ units

SUPERSCRIPT = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹", "0123456789")


def clean_unit(u):
    """Normalize a raw unit string into a comparable form."""
    if not u:
        return ""
    u = u.translate(SUPERSCRIPT)
    u = u.replace("\\^", "^").replace("\\", "")
    u = u.replace("µ", "u").replace("μ", "u").replace("＾", "^")
    u = u.replace("×", "x").replace("·", "")
    u = re.sub(r"\s+", "", u).lower()
    u = u.replace("cells", "").replace("count", "")
    # "10 9/L" and "109/L" both mean 10^9/L; the registry strips superscripts.
    u = re.sub(r"^x?10\^?(\d{1,2})/", r"10^\1/", u)
    u = u.replace("mm^3", "mm3").replace("mm³", "mm3")
    u = u.replace("/cumm", "/mm3").replace("/cmm", "/mm3")
    return u


# multiplicative factor to reach the canonical unit, per analyte
CONVERSIONS = {
    "10^9/L": {
        "10^9/l": 1.0,
        "10^3/ul": 1.0,      # 10^3/uL == 10^9/L exactly
        "10^3/mm3": 1.0,
        "g/l": None,
        "/ul": 1e-3,
        "/mm3": 1e-3,
        "/l": 1e-9,
        "10^6/l": 1e-3,
        "10^12/l": 1e3,
        # "" is resolved by _infer_count_unit, never by a fixed factor
    },
    "g/dL": {"g/dl": 1.0, "g/l": 0.1, "mg/dl": 1e-3, "": 1.0},
    "mg/dL": {"mg/dl": 1.0, "umol/l": None, "mmol/l": None, "": 1.0},
    "mL/min": {
        "ml/min": 1.0,
        "ml/min/1.73m2": 1.0,
        "ml/min/1.73m^2": 1.0,
        "ml/min/1.73": 1.0,
        "": 1.0,
    },
    "U/L": {"u/l": 1.0, "iu/l": 1.0, "": 1.0},
    "ratio": {"": 1.0},
    "s": {"s": 1.0, "sec": 1.0, "seconds": 1.0, "": 1.0},
    "%": {"%": 1.0, "": 1.0},
    # A QTc reported in seconds is 1000x a QTc in ms. Without this the
    # conversion fails and 0.485 s reads as 0.485 ms.
    "ms": {"ms": 1.0, "msec": 1.0, "millisecond": 1.0,
           "s": 1000.0, "sec": 1000.0, "seconds": 1000.0, "": 1.0},
    "mmHg": {"mmhg": 1.0, "": 1.0},
    "kg/m^2": {"kg/m2": 1.0, "kg/m^2": 1.0, "": 1.0},
}

# analyte-specific molar conversions (molar mass based, not a plain factor table)
MOLAR = {
    ("CREATININE", "umol/l"): 1 / 88.4,     # umol/L -> mg/dL
    ("BILIRUBIN", "umol/l"): 1 / 17.104,    # umol/L -> mg/dL
    ("BILIRUBIN", "mmol/l"): 1000 / 17.104,
    ("CREATININE", "mmol/l"): 1000 / 88.4,
    ("HEMOGLOBIN", "mmol/l"): 1.611,        # mmol/L -> g/dL
}


class UnitError(ValueError):
    pass


# Cutoff separating a 10^9/L value from a per-uL value when the text gives no
# unit. Registry prose writes the same threshold as "ANC >= 1.5" (10^9/L) or
# "ANC >= 1500" (per-uL); the two differ by 1000x, so a guess is wrong half the
# time. The cutoff is per-analyte because the plausible ranges differ by two
# orders of magnitude between them -- a shared cutoff would read the very common
# "platelets >= 100" as 0.1 x10^9/L.
#
#   analyte      typical 10^9/L    typical per-uL      cutoff
#   ANC             0.5 -  10        500 - 10,000        100
#   LYMPHOCYTES     0.2 -   5        200 -  5,000        100
#   WBC             2   -  50      2,000 - 50,000        500
#   PLATELETS      50   - 450     50,000 - 450,000     2,000
COUNT_UNIT_CUTOFF = {
    "ANC": 100,
    "LYMPHOCYTES": 100,
    "WBC": 500,
    "PLATELETS": 2000,
}
COUNT_ANALYTES = set(COUNT_UNIT_CUTOFF)


def _infer_count_unit(analyte, value):
    """Resolve a unitless cell count against that analyte's plausible range."""
    return "10^9/l" if value < COUNT_UNIT_CUTOFF[analyte] else "/ul"


def to_canonical(analyte, value, raw_unit):
    """Convert `value` in `raw_unit` to the analyte's canonical unit.

    Returns (converted_value, canonical_unit). Raises UnitError when the unit
    is not one we can convert -- callers must NOT guess.
    """
    if analyte not in CANONICAL:
        raise UnitError(f"unknown analyte {analyte!r}")
    canon = CANONICAL[analyte]
    u = clean_unit(raw_unit)

    if not u and analyte in COUNT_ANALYTES:
        u = _infer_count_unit(analyte, value)

    if (analyte, u) in MOLAR:
        return round(value * MOLAR[(analyte, u)], 6), canon

    table = CONVERSIONS[canon]
    if u not in table:
        raise UnitError(f"unit {raw_unit!r} (parsed {u!r}) not convertible for {analyte}")
    factor = table[u]
    if factor is None:
        raise UnitError(f"unit {raw_unit!r} needs a molar conversion for {analyte}")
    return round(value * factor, 6), canon


# -------------------------------------------------- reference (ULN / LLN)

# Fallback adult reference limits, used ONLY when the patient record carries no
# institutional limit for the analyte. Every use is flagged in the verdict so
# the UI can say the number came from a default, not from the patient's lab.
REFERENCE_LIMITS = {
    # analyte: (LLN, ULN) in canonical units
    "BILIRUBIN": (0.2, 1.2),
    "AST": (10.0, 40.0),
    "ALT": (7.0, 40.0),
    "ALP": (44.0, 130.0),
    "CREATININE": (0.6, 1.2),
    "INR": (0.8, 1.2),
    "PT": (11.0, 13.5),
    "APTT": (25.0, 35.0),
    "ALBUMIN": (3.5, 5.0),
    "HEMOGLOBIN": (12.0, 17.0),
    "ANC": (1.8, 7.7),
    "PLATELETS": (150.0, 400.0),
    "WBC": (4.0, 11.0),
    "LYMPHOCYTES": (1.0, 4.8),
}


def reference_limit(analyte, kind):
    """Default ULN/LLN for an analyte, or None if we have no defensible value."""
    lims = REFERENCE_LIMITS.get(analyte)
    if not lims:
        return None
    return lims[1] if kind == "uln" else lims[0]
