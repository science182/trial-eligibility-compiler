"""Drug-class, event, and anchor vocabulary for WASHOUT.

A washout predicate is only useful if we can name the thing whose date we need,
because evaluation is `last_date[class] + window`. A window we cannot attach to
a lookup key is not compiled at all -- it falls through to FREE_TEXT rather than
becoming a predicate that can never be evaluated.

Classes are the keys into PatientRecord.last_dose_dates, so they must match what
extract.py will populate.
"""

import re

# Ordered longest-first within each entry. The class whose mention sits nearest
# before a duration window wins that window.
DRUG_CLASS_PATTERNS = [
    # --- targeted therapy -------------------------------------------------
    ("EGFR_TKI",
     r"osimertinib|erlotinib|gefitinib|afatinib|dacomitinib|icotinib|"
     r"sunvozertinib|EGFR[\s-]*TKI|EGFR\s+inhibitor|EGFR[\s-]*targeted"),
    ("ALK_TKI",
     r"alectinib|lorlatinib|crizotinib|brigatinib|ceritinib|ensartinib|"
     r"ALK[\s-]*TKI|ALK\s+inhibitor"),
    ("TKI",
     r"tyrosine\s+kinase\s+inhibitor|small\s+molecule\s+inhibitor|\bTKIs?\b|"
     r"cabozantinib|lenvatinib|sunitinib|sorafenib|regorafenib|apatinib|"
     r"anlotinib|nintedanib|selpercatinib|pralsetinib|capmatinib|tepotinib|"
     r"savolitinib|entrectinib|larotrectinib|dabrafenib|trametinib"),
    # --- immunotherapy ----------------------------------------------------
    ("CHECKPOINT_INHIBITOR",
     r"pembrolizumab|nivolumab|atezolizumab|durvalumab|cemiplimab|sintilimab|"
     r"tislelizumab|camrelizumab|toripalimab|ipilimumab|tremelimumab|"
     r"anti[\s-]*PD[\s-]*[L]?1|PD[\s-]*[L]?1\s+(?:inhibitor|antibody|blockade)|"
     r"anti[\s-]*CTLA[\s-]*4|CTLA[\s-]*4\s+inhibitor|"
     r"immune\s+checkpoint\s+inhibitor|checkpoint\s+inhibitor|\bICIs?\b"),
    ("IMMUNOTHERAPY", r"immunotherapy|immune\s+therapy"),
    # --- cytotoxic --------------------------------------------------------
    ("ANTHRACYCLINE", r"anthracyclines?|doxorubicin|epirubicin"),
    ("CHEMOTHERAPY",
     r"cytotoxic\s+chemotherapy|platinum[\s-]*based\s+(?:doublet\s+)?"
     r"chemotherapy|chemotherapy|chemo\b|pemetrexed|docetaxel|paclitaxel|"
     r"carboplatin|cisplatin|gemcitabine|etoposide"),
    ("MONOCLONAL_ANTIBODY",
     r"monoclonal\s+antibod(?:y|ies)|bevacizumab|ramucirumab|amivantamab|"
     r"\bmAbs?\b"),
    # --- procedures -------------------------------------------------------
    ("RADIOTHERAPY",
     # "radiation pneumonitis" / "radiation-induced injury" name a CONDITION,
     # not a course of radiotherapy the patient received.
     r"radiotherapy|radiation\s+therapy|chemoradiation|chemoradiotherapy|"
     r"\bradiation\b(?!\s*[\s-]?(?:pneumonitis|induced|related))|\bSBRT\b|stereotactic\s+(?:body\s+)?radi|"
     r"stereotactic\s+radiosurgery|\bSRS\b|palliative\s+radi|thoracic\s+radi"),
    ("SURGERY",
     r"major\s+surgery|minor\s+surgery|surgical\s+(?:procedure|operation|"
     r"resection)|\bsurgery\b|thoracotomy|lobectomy|pneumonectomy|"
     r"segmentectomy|\bresection\b"),
    # --- concomitant medication ------------------------------------------
    ("CORTICOSTEROIDS",
     r"systemic\s+corticosteroids?|corticosteroids?|glucocorticoids?|"
     r"prednisone|prednisolone|dexamethasone|\bsteroids?\b"),
    ("IMMUNOSUPPRESSANTS",
     r"immunosuppressive\s+(?:therapy|medication|treatment|agent)|"
     r"immunosuppressants?|immune\s+suppressive"),
    ("CYP_MODULATOR",
     r"(?:strong\s+)?CYP\s*\d[A-Z]\d?\s*(?:inhibitors?|inducers?|substrates?)|"
     r"CYP\s*\d[A-Z]\d?|P[\s-]*glycoprotein|\bP[\s-]*gp\b"),
    ("ANTICOAGULANT",
     r"anticoagulants?|warfarin|heparin|enoxaparin|dalteparin|\bDOACs?\b"),
    ("ANTIBIOTICS",
     r"systemic\s+anti[\s-]*(?:bacterial|fungal|infective|microbial)|"
     r"antibiotics?|antimicrobials?|anti[\s-]*infectives?"),
    ("LIVE_VACCINE",
     r"live\s*(?:,\s*)?(?:attenuated\s+)?vaccin\w*|live[\s-]*virus\s+vaccin\w*|"
     r"attenuated\s+vaccin\w*"),
    ("VACCINE", r"vaccinations?|vaccines?"),
    ("TRANSFUSION",
     r"blood\s+transfusions?|platelet\s+transfusions?|transfusions?|"
     r"blood\s+products?|erythropoiesis[\s-]*stimulating|"
     r"(?:granulocyte\s+)?colony[\s-]*stimulating\s+factor|\bG[\s-]*CSF\b|"
     r"growth\s+factors?"),
    ("HERBAL",
     r"traditional\s+chinese\s+medicine|herbal\s+supplements?|chinese\s+patent"),
    # --- study participation ---------------------------------------------
    ("INVESTIGATIONAL",
     r"investigational\s+(?:agents?|drugs?|products?|devices?|therap\w+|"
     r"medicinal)|another\s+clinical\s+(?:study|trial)|other\s+clinical\s+"
     r"(?:study|trial)|interventional\s+clinical\s+study|study\s+drug\s+"
     r"in\s+another"),
    # --- generic anticancer, last so specific classes win ------------------
    ("ANTICANCER_THERAPY",
     r"systemic\s+anti[\s-]*(?:cancer|tumou?r|neoplastic)\s+(?:therapy|"
     r"treatment|agents?)|anti[\s-]*(?:cancer|tumou?r)\s+(?:therapy|treatment)|"
     r"systemic\s+(?:therapy|treatment)|anticancer\s+therapy|"
     r"CNS[\s-]*directed\s+treatment"),
]

# Datable clinical events. Same arithmetic (event date + window), different
# field on the patient record, so they are tracked separately from drug classes.
EVENT_PATTERNS = [
    # Adjectives intervene freely: "other ACTIVE malignancy", "another
    # INVASIVE malignancy", "second PRIMARY cancer".
    ("SECOND_MALIGNANCY",
     r"(?:other|another|secondary|second|concurrent|prior|previous)\s+"
     r"(?:\w+\s+){0,2}?(?:malignan\w+|cancers?|carcinomas?|tumou?rs?)|"
     r"malignan\w+\s+other\s+than|history\s+of\s+(?:other\s+)?malignan\w+"),
    ("MYOCARDIAL_INFARCTION",
     r"myocardial\s+infarction|heart\s+attack|\bMI\b"),
    ("ANGINA", r"unstable\s+angina|angina\s+pectoris|\bangina\b"),
    ("ARRHYTHMIA",
     r"cardiac\s+arrhythmias?|\barrhythmias?\b|atrial\s+fibrillation|"
     r"ventricular\s+(?:tachycardia|fibrillation)"),
    ("HEART_FAILURE",
     r"congestive\s+heart\s+failure|cardiac\s+insufficiency|\bCHF\b|"
     r"heart\s+failure"),
    ("CARDIAC_DISEASE",
     r"(?:clinically\s+significant\s+|significant\s+)?cardiac\s+"
     r"(?:disease|event|disorder)s?|cardiovascular\s+(?:disease|event)s?"),
    ("TOXICITY",
     r"immune[\s-]*(?:mediated|related)\s+adverse\s+events?|\birAEs?\b|"
     r"adverse\s+events?|toxicit(?:y|ies)|\bAEs?\b"),
    ("ORGAN_TRANSPLANT",
     r"(?:allogeneic\s+)?(?:organ|hematopoietic\s+stem\s+cell|bone\s+marrow)"
     r"\s+transplant\w*|stem\s+cell\s+transplant\w*"),
    ("AUTOIMMUNE_DISEASE",
     r"active\s+autoimmune\s+disease|autoimmune\s+diseases?"),
    ("WOUND",
     r"non[\s-]*healing\s+wounds?|unhealed\s+(?:surgical\s+)?(?:incisions?|"
     r"wounds?)|bone\s+fractures?|serious\s+(?:or\s+nonhealing\s+)?wounds?"),
    ("STROKE", r"strokes?|cerebrovascular\s+accident|transient\s+ischemic|\bTIA\b"),
    ("GI_BLEED",
     r"gastrointestinal\s+bleed\w*|\bGI\s+bleed\w*|hemoptysis|haemoptysis|"
     r"hematemesis|gastrointestinal\s+perforation|abdominal\s+fistula"),
    ("THROMBOSIS",
     r"venous\s+thrombosis|thromboembolic|deep\s+vein\s+thrombosis|"
     r"pulmonary\s+embolism|\bDVT\b|\bPE\b"),
    ("DISEASE_PROGRESSION",
     r"disease\s+progression|progressed?|recurrence|relapsed?"),
    ("INFECTION_HOSPITALIZATION",
     r"hospitali[sz]ation\s+for|(?:severe|serious)\s+infections?|"
     r"active\s+infection"),
]

# What the window is measured TO.
ANCHOR_PATTERNS = [
    ("randomization", r"randomi[sz]ation|randomi[sz]ed"),
    ("registration", r"registration|registered"),
    ("first_dose",
     r"first\s+(?:study\s+)?(?:dose|administration|treatment)|"
     r"first\s+dose\s+of|start\s+of\s+(?:study\s+)?(?:treatment|therapy|drug)|"
     r"initiation\s+of\s+(?:study\s+)?(?:treatment|therapy)|"
     r"cycle\s*1\s*day\s*1|\bC1D1\b|study\s+treatment\s+start|"
     r"first\s+(?:administration|dosing)|study\s+drug\s+administration"),
    ("enrollment",
     r"enroll?ment|enroll?ed|study\s+entry|entering\s+the\s+study|inclusion"),
    ("screening", r"screening"),
    ("consent", r"informed\s+consent|signing\s+the\s+ICF|\bICF\b"),
    ("study_start", r"study\s+start|start\s+of\s+the\s+study|study\s+treatment"),
]

# Phrases that make a duration something other than a washout. These sentences
# contain a number and a time unit but nothing datable to gate eligibility on.
NOT_A_WASHOUT = re.compile(
    r"life\s+expectancy|expected\s+survival|predicted\s+survival|"
    r"survival\s+of\s+at\s+least|projected\s+life|"
    r"years\s+(?:of\s+age|old)|aged?\s+\d|age\s+(?:of\s+)?\d|"
    r"menses|menstruation|menopaus|amenorrh|childbearing|contracepti|"
    r"breast\s*feed|lactat|pregnan|donat(?:e|ing)\s+sperm",
    re.I,
)

# "a minimum of 12 weeks ON continued pembrolizumab" states how long therapy
# ran, not how long since it stopped.
TREATMENT_DURATION = re.compile(
    r"^\s*(?:on|of)\s+(?:continued|ongoing|treatment|therapy)|"
    r"^\s*on\s+\w+\s+(?:therapy|treatment)|^\s*of\s+(?:adjuvant|neoadjuvant)",
    re.I,
)

# A window that qualifies a measurement, not a therapy:
# "Hemoglobin > 9.0 g/dL (within 28 days prior to randomization)".
MEASUREMENT_SUBJECT = re.compile(
    r"\b(?:laborator\w+|lab\s+(?:test|value|result)|test(?:s|ed|ing)?|"
    r"assessments?|scans?|imaging|\bCT\b|\bMRI\b|\bPET\b|electrocardiogram|"
    r"\bECG\b|\bEKG\b|biopsy|examinations?|measurements?|obtained|drawn|"
    r"performed|documented|evaluat\w+)\b",
    re.I,
)


# Classes that count as prior ANTICANCER therapy. Corticosteroids, antibiotics,
# vaccines, transfusions, and anticoagulants are washout subjects only -- having
# had them is not a treatment-history requirement.
ANTICANCER_CLASSES = {
    "EGFR_TKI", "ALK_TKI", "TKI", "CHECKPOINT_INHIBITOR", "IMMUNOTHERAPY",
    "ANTHRACYCLINE", "CHEMOTHERAPY", "MONOCLONAL_ANTIBODY", "RADIOTHERAPY",
    "SURGERY", "ANTICANCER_THERAPY",
}

# "prior" also attaches to things that are not therapy at all. These hold even
# when a therapy class is named in the same sentence ("previous significant
# bowel resection", "hypersensitivity to excipients of osimertinib").
NOT_PRIOR_THERAPY_HARD = re.compile(
    r"transplant\w*|hysterectom\w*|informed\s+consent|"
    r"(?:bowel|gastric|intestinal)\s+resection|lap\s+band|"
    r"hypersensitiv\w*|allerg\w*|excipients?|"
    r"inflammatory\s+bowel|hepatitis\s+B\s+virus\s+\(HBV\)\s+anti",
    re.I,
)

# Recovery-from-toxicity language. This means "prior therapy" only in the
# generic sense; when a specific class is named ("Grade 3 toxicity to a prior
# checkpoint inhibitor") the criterion IS a treatment-history exclusion.
NOT_PRIOR_THERAPY_SOFT = re.compile(
    r"toxicit\w*|adverse\s+events?|recovered\s+from|unresolved|autoimmune",
    re.I,
)


def _scan(patterns, text):
    """All vocabulary hits with positions, longest-match-wins on overlap."""
    hits = []
    for name, pat in patterns:
        for m in re.finditer(pat, text, re.I):
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


# A specific class implies its parent. "EGFR tyrosine kinase inhibitor" matches
# both EGFR_TKI and the generic TKI at different spans, so overlap resolution
# never sees them -- but emitting both means the generic one abstains for want
# of its own date and drags the whole criterion to UNDETERMINED.
CLASS_PARENTS = {
    "EGFR_TKI": "TKI", "ALK_TKI": "TKI",
    "CHECKPOINT_INHIBITOR": "IMMUNOTHERAPY",
    "ANTHRACYCLINE": "CHEMOTHERAPY",
}


def drop_redundant_parents(hits):
    """Remove a parent class when one of its children is also present."""
    names = {n for _, _, n in hits}
    redundant = {p for n, p in CLASS_PARENTS.items() if n in names}
    return [h for h in hits if h[2] not in redundant]


def find_classes(text):
    return drop_redundant_parents(_scan(DRUG_CLASS_PATTERNS, text))


def find_events(text):
    return _scan(EVENT_PATTERNS, text)


def find_anchor(text, pos):
    """Anchor named closest after `pos`; falls back to the whole string."""
    best = None
    for name, pat in ANCHOR_PATTERNS:
        for m in re.finditer(pat, text, re.I):
            if m.start() < pos:
                continue
            if best is None or m.start() < best[0]:
                best = (m.start(), name)
    if best:
        return best[1], False
    for name, pat in ANCHOR_PATTERNS:
        if re.search(pat, text, re.I):
            return name, False
    return "first_dose", True      # inferred
