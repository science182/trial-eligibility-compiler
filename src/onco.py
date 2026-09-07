"""Histology, stage, and biomarker vocabulary.

Separate from units.py (lab analytes) and drugs.py (therapy classes) because
these three types describe the tumour rather than the patient's labs or
treatment history, and they share the stage/gene notation.
"""

import re

# ------------------------------------------------------------- histology

HISTOLOGY_PATTERNS = [
    ("SCLC",
     r"small\s+cell\s+lung\s+(?:cancer|carcinoma)|\bSCLC\b|"
     r"small[\s-]cell\s+(?:histology|transformation)"),
    ("LCNEC",
     r"large\s+cell\s+neuroendocrine|\bLCNEC\b"),
    ("NSCLC_NONSQUAMOUS",
     r"non[\s-]*squamous\s+(?:cell\s+)?(?:NSCLC|non[\s-]*small[\s-]*cell|"
     r"histology|carcinoma)?|nonsquamous"),
    ("NSCLC_SQUAMOUS",
     r"squamous\s+(?:cell\s+)?(?:NSCLC|non[\s-]*small[\s-]*cell\s+lung\s+"
     r"(?:cancer|carcinoma)|lung\s+(?:cancer|carcinoma)|histology)|"
     r"lung\s+squamous\s+cell\s+carcinoma|\bLUSC\b"),
    ("ADENOCARCINOMA",
     r"lung\s+adenocarcinoma|adenocarcinoma\s+of\s+the\s+lung|adenocarcinoma"),
    ("NSCLC",
     r"non[\s-]*small[\s-]*cell\s+lung\s+(?:cancer|carcinoma)|\bNSCLC\b|"
     r"non[\s-]*small[\s-]*cell\s+carcinoma\s+of\s+the\s+lung|"
     r"non[\s-]*small\s+cell\s+lung"),
    ("LARGE_CELL", r"large\s+cell\s+carcinoma"),
    ("SARCOMATOID", r"sarcomatoid"),
    ("SOLID_TUMOR", r"(?:advanced\s+)?solid\s+tumou?rs?|solid\s+malignanc\w+"),
]

# "squamous" appears constantly in prior-malignancy carve-outs and in basket
# trials listing other diseases. Neither is a statement about the lung tumour.
HISTOLOGY_TRAPS = re.compile(
    r"squamous\s+cell\s+(?:skin|carcinoma\s+of\s+the\s+skin)|"
    r"skin\s+cancer|basal\s+cell|cervical|head\s+and\s+neck|oesophag|esophag|"
    r"bladder|urothelial|breast|pancrea|colorect|melanoma|prostate|"
    r"hepatocellular|gastric|renal\s+(?:pelvis|cell)|"
    # "malignancy other than NSCLC" names the tumour only to carve it out.
    r"other\s+than\s+(?:non|small|lung)",
    re.I,
)

# Histologies a trial rules out rather than requires.
HISTOLOGY_EXCLUDED_CUE = re.compile(
    r"\b(?:mixed|component\s+of|transformation|excluding|except|not\s+"
    r"(?:including|eligible)|no\b|without)\b", re.I)

# "NSCLC" appears as background in most criteria of an NSCLC trial ("prior
# treatment for stage IIIB/IV NSCLC"), where it states no histology
# requirement. A generic term needs an explicit diagnosis claim nearby.
HISTOLOGY_CLAIM_CUE = re.compile(
    r"histolog\w*|cytolog\w*|patholog\w*|confirmed|diagnos\w*|proven|"
    r"documented|biops\w+|\bproof\b|patients?\s+with|subjects?\s+with|"
    r"participants?\s+with|must\s+have", re.I)

# Subtypes are inherently restrictive: naming squamous, adenocarcinoma, or SCLC
# is always a claim about which tumour qualifies, cue or not.
HISTOLOGY_SUBTYPES = {"NSCLC_SQUAMOUS", "NSCLC_NONSQUAMOUS", "ADENOCARCINOMA",
                      "SCLC", "LCNEC", "LARGE_CELL", "SARCOMATOID"}


# ----------------------------------------------------------------- stage

# Ordinal value per stage code. Bare stages span their substages, so a range
# ending at "III" must reach IIIC -- see stage_bounds().
STAGE_VALUES = {
    "0": 0.0,
    "I": 1.0, "IA": 1.1, "IA1": 1.11, "IA2": 1.12, "IA3": 1.13, "IB": 1.2,
    "II": 2.0, "IIA": 2.1, "IIB": 2.2,
    "III": 3.0, "IIIA": 3.1, "IIIB": 3.2, "IIIC": 3.3,
    "IV": 4.0, "IVA": 4.1, "IVB": 4.2,
}
BARE_STAGES = {"0", "I", "II", "III", "IV"}

STAGE_TOKEN = r"(?:IV|III|II|I)[ABC]?[123]?|0"
STAGE_RE = re.compile(rf"\b({STAGE_TOKEN})\b")

# Descriptive stage language. Only unambiguous terms are mapped; bare
# "advanced" spans III and IV in practice and is left uncompiled.
STAGE_DESCRIPTORS = [
    ("metastatic", {"IV", "IVA", "IVB"},
     r"\bmetastatic\b|\bmetastases\b|\bstage\s+4\b|\bdistant\s+metastas"),
    ("locally_advanced", {"III", "IIIA", "IIIB", "IIIC"},
     r"locally[\s-]advanced|\bLA\s+NSCLC\b"),
]


def stage_bounds(code):
    """(low, high) ordinal span of a stage code; bare stages cover substages."""
    v = STAGE_VALUES[code]
    if code in BARE_STAGES:
        return v, v + 0.99
    return v, v


def expand_stage_range(lo, hi):
    """All stage codes between two endpoints, inclusive."""
    low = stage_bounds(lo)[0]
    high = stage_bounds(hi)[1]
    if low > high:
        low, high = stage_bounds(hi)[0], stage_bounds(lo)[1]
    return sorted((c for c, v in STAGE_VALUES.items() if low <= v <= high),
                  key=lambda c: STAGE_VALUES[c])


# ------------------------------------------------------------- biomarker

# Short symbols are matched case-sensitively: "MET" and "RET" collide with the
# ordinary words "met" and (in "interpreted") "ret" under re.I.
GENE_PATTERNS = [
    # HER2 expands to "human EPIDERMAL GROWTH FACTOR RECEPTOR 2", which
    # contains EGFR's long form verbatim. Without these guards a HER2
    # criterion also compiles an EGFR predicate.
    ("EGFR",
     r"\bEGFRm?\b|(?<!human\s)epidermal\s+growth\s+factor\s+receptor(?!\s*2)",
     re.I),
    ("ALK", r"\bALK\b|anaplastic\s+lymphoma\s+kinase", 0),
    ("ROS1", r"\bROS-?1\b", re.I),
    ("KRAS", r"\bKRAS\b|\bK-?ras\b", re.I),
    ("NRAS", r"\bNRAS\b", 0),
    ("BRAF", r"\bBRAF\b", re.I),
    ("RET", r"\bRET\b|rearranged\s+during\s+transfection", 0),
    ("MET", r"\bMET\b|\bc-MET\b|mesenchymal[\s-]epithelial", 0),
    ("HER2", r"\bHER-?2\b|\bERBB2\b", re.I),
    ("NTRK", r"\bNTRK\d?\b|\bTRK\b", re.I),
    ("PD_L1", r"PD-?L1|programmed\s+death[\s-]ligand", re.I),
    ("BRCA", r"\bBRCA[12]?\b", re.I),
    ("AXL", r"\bAXL\b", 0),
    ("LKB1", r"\bLKB1\b|\bSTK11\b", re.I),
    ("KEAP1", r"\bKEAP1\b", re.I),
    ("TP53", r"\bTP53\b|\bp53\b", re.I),
]

# Specific alterations, tried before the generic ones.
ALTERATION_PATTERNS = [
    ("EXON19DEL", r"exon\s*19\s*(?:deletion|del)\w*|\bex19del\b|\b19\s*del\b"),
    ("L858R", r"\bL858R\b"),
    ("T790M", r"\bT790M\b"),
    ("C797X", r"\bC797[XS]\b"),
    ("EXON20INS", r"exon\s*20\s*insertion\w*|\bex20ins\b"),
    ("EXON14SKIP", r"exon\s*14\s*(?:skipping|skip)\w*"),
    ("G12C", r"\bG12C\b"),
    ("G12D", r"\bG12D\b"),
    ("G12V", r"\bG12V\b"),
    ("V600", r"\bV600[EK]?\b"),
    ("G719X", r"\bG719[XASC]\b"),
    ("S768I", r"\bS768I\b"),
    ("L861Q", r"\bL861Q\b"),
    ("FUSION", r"\bfusions?\b|rearrangement\w*|translocation\w*|\bfused\b"),
    ("AMPLIFICATION", r"amplificat\w*|\bamplified\b"),
    ("OVEREXPRESSION",
     r"overexpress\w*|\bexpression\b|\bTPS\b|\bCPS\b|\btumou?r\s+proportion\s+score\b"),
    # "wild type" is a claim about the gene, so it needs to be an alteration
    # token; BIOMARKER_NEGATION then flips `required` to False.
    ("MUTATION",
     r"mutation\w*|\bmutant\b|\bmutated\b|\bmut\b|"
     r"wild[\s-]?type|non[\s-]mutated|unmutated"),
    ("POSITIVE", r"\bpositive\b|\bpositivity\b"),
]

# Alterations that name no specific variant. A specific one in the same window
# outranks these -- "sensitizing mutations (Exon19del and/or L858R)" claims the
# two variants, not the noun "mutations".
GENERIC_ALTERATIONS = {"MUTATION", "POSITIVE", "FUSION", "AMPLIFICATION",
                       "OVEREXPRESSION"}

# "fusion proteins" in a hypersensitivity clause is not a gene fusion.
ALTERATION_TRAPS = re.compile(
    r"fusion\s+proteins?|humani[sz]ed\s+antibod|chimeric", re.I)

# The criterion asserts the marker is ABSENT.
BIOMARKER_NEGATION = re.compile(
    r"\b(?:no|not|without|negative|absence|lack(?:ing)?|free\s+of|"
    r"wild[\s-]?type|\bwt\b|non[\s-]mutated|unmutated)\b", re.I)

# Wording that means "any of these genes", where naming one is not a claim
# about the patient -- typically a definition of actionable alterations.
GENE_LIST_CUE = re.compile(
    r"such\s+as|including|e\.?g\.?|for\s+which|for\s+example", re.I)


def scan(patterns, text):
    """Longest-match-wins scan over (name, pattern) or (name, pattern, flags)."""
    hits = []
    for entry in patterns:
        if len(entry) == 3:
            name, pat, flags = entry
        else:
            name, pat = entry
            flags = re.I
        for m in re.finditer(pat, text, flags):
            hits.append((m.start(), m.end(), name))
    hits.sort()
    kept = []
    for s, e, n in hits:
        if kept and s < kept[-1][1]:
            if (e - s) > (kept[-1][1] - kept[-1][0]):
                kept[-1] = (s, e, n)
            continue
        kept.append((s, e, n))
    return kept
