"""Named comorbidity vocabulary.

COMORBIDITY compiles only when the criterion NAMES a condition. Registry text
is full of unnamed catch-alls -- "any other concurrent severe and/or
uncontrolled medical condition that would, in the investigator's judgement,
contraindicate participation" -- which state a real restriction but nothing a
patient record can be checked against. Those stay FREE_TEXT.

Qualifiers are tracked separately because they decide the verdict: "active
brain metastases" blocks, while "treated, stable brain metastases are eligible"
does not, and the condition token is identical in both.
"""

import re

CONDITION_PATTERNS = [
    # --- CNS --------------------------------------------------------------
    ("BRAIN_METASTASES",
     r"brain\s+metastas\w*|cerebral\s+metastas\w*|CNS\s+metastas\w*|"
     r"central\s+nervous\s+system\s+metastas\w*|intracranial\s+metastas\w*|"
     r"brain\s+mets\b|CNS\s+lesions?|"
     # "metastases TO the brain stem" reverses the usual word order
     r"metastas\w*\s+to\s+(?:the\s+)?brain(?:\s+stem)?"),
    ("LEPTOMENINGEAL_DISEASE",
     r"leptomeningeal\s+(?:disease|metastas\w*|carcinomatosis)|"
     r"meningeal\s+(?:metastas\w*|carcinomatosis)|carcinomatous\s+meningitis|"
     r"meningeal\s+disease|\bmeninges\b"),
    ("SPINAL_CORD_COMPRESSION", r"spinal\s+cord\s+compression"),
    ("PRIMARY_CNS_TUMOR",
     r"primary\s+(?:central\s+nervous\s+system|CNS)\s+(?:tumou?rs?|malignanc\w+)"),
    ("SEIZURE_DISORDER",
     r"\bseizures?\b|\bepilep\w+|encephalitis|\bmeningitis\b(?!\s*,)|"
     r"organic\s+brain\s+disease"),
    ("NEUROPATHY", r"peripheral\s+neuropath\w+|\bneuropath(?:y|ies)\b"),
    # --- cardiac ----------------------------------------------------------
    ("HEART_FAILURE",
     r"congestive\s+heart\s+failure|\bCHF\b|heart\s+failure|"
     r"cardiac\s+insufficiency|cardiomyopath\w+"),
    ("MYOCARDIAL_INFARCTION",
     r"myocardial\s+infarction|heart\s+attack|acute\s+coronary\s+syndrome"),
    ("ANGINA", r"unstable\s+angina|angina\s+pectoris|\bangina\b"),
    ("ARRHYTHMIA",
     r"cardiac\s+arrhythmias?|\barrhythmias?\b|atrial\s+fibrillation|"
     r"ventricular\s+(?:tachycardia|fibrillation)|"
     r"(?:second|third)[\s-]degree\s+(?:heart|atrioventricular)\s+block|"
     r"bundle\s+branch\s+block"),
    ("LONG_QT_SYNDROME", r"long\s+QT\s+syndrome|QT\s+prolongation"),
    ("PERICARDIAL_EFFUSION", r"pericardial\s+effusions?"),
    ("HYPERTENSION", r"\bhypertension\b|high\s+blood\s+pressure"),
    ("VALVULAR_DISEASE", r"valvular\s+(?:heart\s+)?disease|valve\s+replacement"),
    # --- vascular ---------------------------------------------------------
    ("STROKE",
     r"\bstrokes?\b|cerebrovascular\s+accident|transient\s+ischemic\s+attack|"
     r"\bTIA\b|intracranial\s+h(?:a?e)morrhage"),
    ("THROMBOSIS",
     r"venous\s+thrombosis|deep\s+vein\s+thrombosis|\bDVT\b|"
     r"pulmonary\s+embolism|thromboembolic\s+events?|arterial\s+thrombosis|"
     r"\bthrombosis\b"),
    ("BLEEDING_DISORDER",
     r"coagulation\s+dysfunction|coagulopath\w+|bleeding\s+(?:diathes\w+|"
     r"disorders?|tendency)|h(?:a?e)morrhag\w+"),
    ("HEMOPTYSIS", r"h(?:a?e)moptysis"),
    # --- pulmonary --------------------------------------------------------
    ("INTERSTITIAL_LUNG_DISEASE",
     r"interstitial\s+lung\s+disease|\bILD\b|interstitial\s+pneumon\w+|"
     r"pulmonary\s+fibrosis|interstitial\s+fibrosis|"
     r"idiopathic\s+pulmonary\s+fibrosis|\bIPF\b"),
    ("PNEUMONITIS",
     r"pneumonitis|radiation\s+pneumonitis|"
     r"radiation[\s-]induced\s+lung\s+(?:injury|disease)|lung\s+injury"),
    ("COPD",
     r"chronic\s+obstructive\s+pulmonary\s+disease|\bCOPD\b|\bemphysema\b"),
    ("PLEURAL_EFFUSION", r"pleural\s+effusions?"),
    ("TUBERCULOSIS", r"\btuberculosis\b|\bTB\b|mycobacterium\s+tuberculosis"),
    ("PNEUMONIA", r"\bpneumonia\b"),
    # --- infection --------------------------------------------------------
    ("HIV",
     r"human\s+immunodeficiency\s+virus|\bHIV\b|acquired\s+immunodeficiency"),
    ("HEPATITIS_B", r"hepatitis\s+B\b|\bHBV\b|\bHBsAg\b"),
    ("HEPATITIS_C", r"hepatitis\s+C\b|\bHCV\b"),
    ("SYPHILIS", r"\bsyphilis\b|treponema\s+pallidum"),
    ("COVID19", r"COVID[\s-]?19|SARS[\s-]?CoV[\s-]?2"),
    ("ACTIVE_INFECTION",
     r"active\s+infections?|systemic\s+infections?|severe\s+infections?|"
     r"uncontrolled\s+infections?|\bsepsis\b|infections?\s+requiring"),
    # --- immune -----------------------------------------------------------
    ("AUTOIMMUNE_DISEASE",
     r"auto[\s-]?immune\s+(?:disease|disorder|condition)s?|auto[\s-]?immune\b"),
    ("IMMUNODEFICIENCY",
     r"immunodeficienc\w+|immune\s+deficienc\w+|immunocompromised"),
    ("ORGAN_TRANSPLANT",
     r"(?:allogeneic\s+|solid\s+)?organ\s+transplant\w*|"
     r"(?:h(?:a?e)matopoietic\s+)?stem\s+cell\s+transplant\w*|"
     r"bone\s+marrow\s+transplant\w*|corneal\s+transplant"),
    # --- GI ---------------------------------------------------------------
    ("INFLAMMATORY_BOWEL_DISEASE",
     r"inflammatory\s+bowel\s+disease|ulcerative\s+colitis|crohn\w*"),
    ("PEPTIC_ULCER", r"peptic\s+ulcers?|gastric\s+ulcers?|duodenal\s+ulcers?"),
    ("GI_PERFORATION",
     r"gastrointestinal\s+perforation|bowel\s+perforation|"
     r"abdominal\s+fistula|gastrointestinal\s+fistula"),
    ("BOWEL_OBSTRUCTION",
     r"bowel\s+obstruction|gastric\s+outlet\s+obstruction|"
     r"gastrointestinal\s+obstruction|intestinal\s+obstruction"),
    ("MALABSORPTION", r"malabsorption\s*(?:syndrome)?"),
    ("GI_IMPAIRMENT",
     r"impairment\s+of\s+gastrointestinal\s+function|"
     r"gastrointestinal\s+(?:disease|disorder|condition)s?|"
     r"(?:inability|unable|difficulty)\s+to\s+swallow|difficulty\s+in\s+swallowing|"
     r"\bdysphagia\b|impaired\s+gastrointestinal\s+absorption"),
    ("PANCREATITIS", r"pancreatitis"),
    ("ASCITES", r"\bascites\b"),
    ("GI_BLEED",
     r"gastrointestinal\s+bleed\w*|\bGI\s+bleed\w*|h(?:a?e)matemesis"),
    # --- hepatic / renal --------------------------------------------------
    ("CIRRHOSIS", r"\bcirrhosis\b|child[\s-]?pugh|hepatic\s+encephalopathy"),
    ("HEPATIC_IMPAIRMENT",
     r"(?:severe\s+)?hepatic\s+(?:disease|impairment|dysfunction|failure)|"
     r"liver\s+(?:failure|dysfunction)"),
    ("RENAL_IMPAIRMENT",
     r"renal\s+(?:failure|insufficiency|impairment|dysfunction)|"
     r"kidney\s+failure|\bdialysis\b|renal\s+replacement\s+therapy|nephritis"),
    # --- endocrine / metabolic -------------------------------------------
    ("DIABETES", r"diabetes\s+mellitus|\bdiabetes\b|diabetic\s+ketoacidosis"),
    ("THYROID_DYSFUNCTION",
     r"thyroid\s+(?:dysfunction|disease|disorder)|hypothyroid\w+|"
     r"hyperthyroid\w+"),
    ("ADRENAL_INSUFFICIENCY",
     r"adrenal\s+insufficienc\w+|cushing\w*|pituitary\s+insufficienc\w+"),
    # --- psychiatric ------------------------------------------------------
    ("PSYCHIATRIC_DISORDER",
     r"psychiatric\s+(?:illness|condition|disorder)s?|\bpsychosis\b|"
     r"mental\s+illness|\bdementia\b|bipolar\s+disorder|\bdepression\b|"
     r"suicidal\s+ideation"),
    ("SUBSTANCE_ABUSE",
     r"substance\s+abuse|drug\s+abuse|alcohol\s+(?:abuse|dependence)|"
     r"alcoholism"),
    # --- ocular -----------------------------------------------------------
    ("OCULAR_DISORDER",
     r"retinal\s+vein\s+occlusion|\bRVO\b|retinal\s+(?:pathology|degenerat\w+|"
     r"detachment)|\bglaucoma\b|\buveitis\b|keratopath\w+|corneal\s+disorders?|"
     r"\bretinopath\w+|ocular\s+(?:disorder|condition|disease)s?"),
    # --- other ------------------------------------------------------------
    ("SECOND_MALIGNANCY",
     r"(?:other|another|secondary|second|concurrent|prior|previous)\s+"
     r"(?:\w+\s+){0,2}?(?:malignan\w+|cancers?|carcinomas?|tumou?rs?)|"
     r"malignan\w+\s+other\s+than"),
    ("BONE_METASTASES", r"bone\s+metastas\w*|osseous\s+metastas\w*"),
    # Drives the conditional lab thresholds ("AST <= 5 x ULN if liver
    # metastases"), so the extractor must be able to resolve it.
    ("LIVER_METASTASES",
     r"liver\s+metastas\w*|hepatic\s+metastas\w*|liver\s+lesions?|"
     r"liver\s+involvement"),
    ("GILBERTS_SYNDROME", r"gilbert\w*"),
    ("NONHEALING_WOUND",
     r"non[\s-]*healing\s+(?:wounds?|ulcers?)|unhealed\s+(?:surgical\s+)?"
     r"(?:incisions?|wounds?)|bone\s+fractures?"),
    ("GVHD", r"graft[\s-]versus[\s-]host"),
]

# Words that qualify how active/severe the condition is. The verdict often
# turns entirely on these: "active brain metastases" blocks where "treated and
# stable brain metastases" does not.
QUALIFIERS = [
    ("uncontrolled", r"uncontrolled|poorly[\s-]controlled|not\s+(?:well\s+)?controlled"),
    ("active", r"\bactive\b|ongoing|current(?:ly)?"),
    ("symptomatic", r"symptomatic|persistently\s+symptomatic"),
    ("severe", r"\bsevere\b|\bserious\b|significant|grade\s*[34]"),
    ("unstable", r"\bunstable\b"),
    ("history_of", r"history\s+of|prior\s+documented|\bprevious\b|\bpast\b"),
    ("stable", r"\bstable\b|asymptomatic|treated\s+and\s+stable|well[\s-]controlled"),
]

# The criterion says patients WITH the condition may still enrol.
PERMITTED = re.compile(
    r"\b(?:are|is|may\s+be|will\s+be|can\s+be)\s+(?:considered\s+)?"
    r"(?:eligible|allowed|permitted|included|enrolled)\b|"
    r"\bmay\s+(?:enrol|enroll|participate|be\s+included)\b|"
    r"\bare\s+not\s+excluded\b|\bis\s+allowed\b|\bare\s+allowed\b",
    re.I,
)

# The criterion says the patient must NOT have it.
CONDITION_NEGATION = re.compile(
    r"\b(?:no|without|absence\s+of|free\s+of|negative\s+for)\s+"
    r"(?:\w+\s+){0,3}?(?=\w)", re.I)

# Contexts where a condition word is not a statement about the patient.
CONDITION_TRAP = re.compile(
    # NOTE: "adequately treated ..." carve-outs are deliberately NOT trapped.
    # They trail the main claim ("any secondary malignancy within 3 years,
    # except adequately treated basal cell carcinoma"), so suppressing the whole
    # criterion loses the requirement itself. First-mention dedupe handles them.
    # the trial's own disease and its assessment
    r"pleural\s+fluid\s+cytology|target\s+lesions?|measurable\s+disease|"
    # drug-safety prose rather than patient history
    r"hypersensitiv\w*|excipients?|formulation|"
    r"risk\s+of\s+(?:QTc|prolonged)|increase\s+the\s+risk\s+of",
    re.I,
)
