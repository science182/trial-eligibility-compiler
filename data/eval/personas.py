"""Fixed patient personas for testing, golden files, and demo rehearsal.

Hand-built from the shape of real NSCLC presentations. These are NOT extracted
from any real record. Spans point into each persona's `report` text so the
provenance path can be exercised before extract.py exists.
"""

from datetime import date

# Every persona is a dict the loader turns into a PatientRecord, so this file
# stays importable without the src package on the path.

MAYA_TORRES = {
    "name": "Maya Torres",
    "index_date": date(2026, 8, 14),
    "report": (
        "ONCOLOGY PROGRESS NOTE\n"
        "64-year-old female. Never-smoker.\n"
        "Diagnosis: stage IV lung adenocarcinoma, biopsy-confirmed 2025-03-11.\n"
        "NGS (tissue, 2025-03-20): EGFR exon 19 deletion detected, VAF 31%. "
        "ALK, ROS1, BRAF, KRAS: no alterations detected. PD-L1 TPS 5%.\n"
        "ECOG performance status 1.\n"
        "Prior therapy: osimertinib 80 mg daily from 2025-04-02, progressed "
        "2026-06-18 (RECIST PD, new hepatic lesions). "
        "Carboplatin/pemetrexed 4 cycles, last dose 2026-07-28.\n"
        "Labs (2026-08-12): ANC 2.6 x10^9/L, platelets 187 x10^9/L, "
        "hemoglobin 11.4 g/dL, creatinine 0.9 mg/dL, total bilirubin 0.7 mg/dL, "
        "AST 31 U/L, ALT 28 U/L (institutional ULN 40 U/L).\n"
        "Imaging: liver metastases present. No brain metastases on MRI "
        "2026-08-02. No interstitial lung disease.\n"
        "Comorbidities: hypertension, controlled on amlodipine. "
        "No autoimmune disease. No prior malignancy.\n"
        # Each negative is written out in full rather than chained ("no pleural
        # effusion, no pericardial effusion" not "no pleural or pericardial
        # effusion"), which is how a real screening ROS reads and what the
        # extractor can actually resolve to a code.
        "Screening review of systems: no leptomeningeal disease, no spinal "
        "cord compression, no pleural effusion, no pericardial effusion, no "
        "pneumonitis, no pneumonia, no active infection, no tuberculosis, no "
        "HIV, no hepatitis B, no hepatitis C, no syphilis, no COVID-19, no "
        "inflammatory bowel disease, no peptic ulcer, no bowel obstruction, "
        "no gastrointestinal perforation, no gastrointestinal bleeding, no "
        "malabsorption, no pancreatitis, no ascites, no cirrhosis, no hepatic "
        "impairment, no renal impairment, no diabetes, no thyroid dysfunction, "
        "no adrenal insufficiency, no psychiatric disorder, no substance "
        "abuse, no glaucoma, no retinopathy, no heart failure, no myocardial "
        "infarction, no angina, no arrhythmia, no long QT syndrome, no "
        "valvular disease, no hypertension crisis, no stroke, no venous "
        "thrombosis, no bleeding disorder, no haemoptysis, no seizures, no "
        "peripheral neuropathy, no organ transplant, no immunodeficiency, no "
        "graft-versus-host disease, no COPD, no non-healing wound, no bone "
        "metastases, no primary CNS tumour, no second malignancy.\n"
        "Treatment history is complete as listed. No investigational agent, "
        "no live vaccine, no vaccine, no antibiotics, no corticosteroids, no "
        "immunosuppressants, no CYP3A4 inhibitor, no anticoagulant, no herbal "
        "supplements, no anthracycline, no radiotherapy, no transfusion and "
        "no surgery at any time prior.\n"
    ),
    "age": 64,
    "sex": "female",
    "histology": "ADENOCARCINOMA",
    "stage": "IV",
    "ecog": 1,
    "biomarkers": [
        ("EGFR", "EXON19DEL", 31.0),
        ("PD_L1", "OVEREXPRESSION", None),
    ],
    "genes_tested": {"EGFR", "ALK", "ROS1", "BRAF", "KRAS", "PD_L1"},
    "labs": {
        # analyte: (value, unit, date, uln)
        "ANC": (2.6, "10^9/L", date(2026, 8, 12), None),
        "PLATELETS": (187, "10^9/L", date(2026, 8, 12), None),
        "HEMOGLOBIN": (11.4, "g/dL", date(2026, 8, 12), None),
        "CREATININE": (0.9, "mg/dL", date(2026, 8, 12), 1.2),
        "BILIRUBIN": (0.7, "mg/dL", date(2026, 8, 12), 1.2),
        "AST": (31, "U/L", date(2026, 8, 12), 40),
        "ALT": (28, "U/L", date(2026, 8, 12), 40),
    },
    "prior_therapies": [
        ("osimertinib", "EGFR_TKI", date(2025, 4, 2), date(2026, 6, 18),
         "PD", 1, True),
        ("carboplatin/pemetrexed", "CHEMOTHERAPY", date(2026, 6, 25),
         date(2026, 7, 28), None, 2, None),
    ],
    "comorbidities": ["HYPERTENSION", "LIVER_METASTASES"],
    # Conditions and therapy classes the screening note explicitly rules out.
    # Anything NOT listed here is unknown, not absent -- which is what drives
    # the Undetermined bucket and the missing-data panel.
    "negative_findings": {
        # conditions
        "BRAIN_METASTASES", "AUTOIMMUNE_DISEASE", "SECOND_MALIGNANCY",
        "INTERSTITIAL_LUNG_DISEASE", "LEPTOMENINGEAL_DISEASE", "HIV",
        "HEPATITIS_B", "HEPATITIS_C", "SPINAL_CORD_COMPRESSION",
        "PLEURAL_EFFUSION", "PERICARDIAL_EFFUSION", "PNEUMONITIS", "PNEUMONIA",
        "ACTIVE_INFECTION", "TUBERCULOSIS", "INFLAMMATORY_BOWEL_DISEASE",
        "PEPTIC_ULCER", "BOWEL_OBSTRUCTION", "GI_PERFORATION", "MALABSORPTION",
        "GI_IMPAIRMENT", "CIRRHOSIS", "HEPATIC_IMPAIRMENT", "RENAL_IMPAIRMENT",
        "DIABETES", "THYROID_DYSFUNCTION", "PSYCHIATRIC_DISORDER",
        "SUBSTANCE_ABUSE", "OCULAR_DISORDER", "HEART_FAILURE",
        "MYOCARDIAL_INFARCTION", "ANGINA", "ARRHYTHMIA", "LONG_QT_SYNDROME",
        "STROKE", "THROMBOSIS", "BLEEDING_DISORDER", "HEMOPTYSIS",
        "SEIZURE_DISORDER", "ORGAN_TRANSPLANT", "IMMUNODEFICIENCY",
        "NONHEALING_WOUND", "PRIMARY_CNS_TUMOR", "ASCITES", "COPD",
        "SYPHILIS", "COVID19", "GVHD", "PANCREATITIS", "GI_BLEED",
        "ADRENAL_INSUFFICIENCY", "VALVULAR_DISEASE", "NEUROPATHY",
        "BONE_METASTASES",
        # therapy classes never received
        "INVESTIGATIONAL", "LIVE_VACCINE", "VACCINE", "ANTIBIOTICS",
        "CORTICOSTEROIDS", "IMMUNOSUPPRESSANTS", "CYP_MODULATOR",
        "TRANSFUSION", "SURGERY", "RADIOTHERAPY", "ANTICOAGULANT", "HERBAL",
        "ANTHRACYCLINE", "PRIOR_MALIGNANCY", "TOXICITY",
        "INFECTION_HOSPITALIZATION", "DISEASE_PROGRESSION",
    },
    "last_dose_dates": {
        "EGFR_TKI": date(2026, 6, 18),
        "CHEMOTHERAPY": date(2026, 7, 28),
    },
    "event_dates": {},
}

PERSONAS = {"maya_torres": MAYA_TORRES}
