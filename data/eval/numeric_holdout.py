"""Held-out cases for metric 9.2.

WHY THIS FILE EXISTS. The main set (numeric_cases.py) found eight genuine
compiler bugs, and those bugs were then fixed. That makes it a regression suite,
not an unbiased estimate -- quoting its post-fix accuracy as the headline would
be tuning on the test set.

These cases were written after the fixes and BEFORE being run even once. The
number they produce is the one to report. Same conventions as the main set:
criterion text verbatim from the corpus, only the patient state constructed.
"""

from numeric_cases import IDX  # noqa: F401  (same index date)

HOLDOUT = [

# ---- lab: unit conversion ------------------------------------------
dict(id="h-01", type="LAB_THRESHOLD", trial="NCT06422403",
     text="Haemoglobin ≥ 8.0 g/dL", incl=True,
     patient={"labs": {"HEMOGLOBIN": (95, "g/L")}},
     gold="met", tags=["unit_conversion"], why="95 g/L = 9.5 g/dL"),
dict(id="h-02", type="LAB_THRESHOLD", trial="NCT07535437",
     text="Absolute neutrophil count (ANC) ≥ 1500 cells/mm^3", incl=True,
     patient={"labs": {"ANC": (0.8, "x10^9/L")}},
     gold="not_met", tags=["unit_conversion"], why="0.8 x10^9/L = 800/mm3"),
dict(id="h-03", type="LAB_THRESHOLD", trial="NCT04933903",
     text="platelets >=100,000/mcL,", incl=True,
     patient={"labs": {"PLATELETS": (99999, "/uL")}},
     gold="not_met", tags=["unit_conversion", "boundary"], why="one short"),
dict(id="h-04", type="LAB_THRESHOLD", trial="NCT05570825",
     text="Creatinine =< 2.0 mg/dL", incl=True,
     patient={"labs": {"CREATININE": (88, "umol/L")}},
     gold="met", tags=["unit_conversion", "molar"], why="88/88.4 = 0.995 mg/dL"),
dict(id="h-05", type="LAB_THRESHOLD", trial="NCT06529822",
     text="WBC ≥ 1.5 K/cumm", incl=True,
     patient={"labs": {"WBC": (1.5, "x10^9/L")}},
     gold="met", tags=["unit_conversion", "boundary"], why="exactly equal"),

# ---- lab: boundary + polarity ---------------------------------------
dict(id="h-06", type="LAB_THRESHOLD", trial="NCT06276283",
     text="Mean resting corrected QT interval (QTcF) > 470 msec.", incl=False,
     patient={"labs": {"QTC": (500, "msec")}},
     gold="not_met", tags=["exclusion"], why="500 > 470, exclusion triggered"),
dict(id="h-07", type="LAB_THRESHOLD", trial="NCT06222489",
     text="Left ventricular ejection fraction (LVEF) <50% by either "
          "echocardiogram (ECHO) or multi-gated acquisition (MUGA) scan",
     incl=False, patient={"labs": {"LVEF": (50, "%")}},
     gold="met", tags=["exclusion", "boundary", "strict"],
     why="exactly 50 is not < 50; exclusion not triggered"),
dict(id="h-08", type="LAB_THRESHOLD", trial="NCT06731270",
     text="Abnormal markers of coagulation as measured by international "
          "normalized ratio (INR) > 2", incl=False,
     patient={"labs": {"INR": (3.5, "")}},
     gold="not_met", tags=["exclusion"], why="3.5 > 2"),
dict(id="h-09", type="LAB_THRESHOLD", trial="NCT05570825",
     text="Creatinine =< 2.0 mg/dL", incl=True,
     patient={"labs": {"CREATININE": (1.99, "mg/dL")}},
     gold="met", tags=["boundary"], why="just under"),

# ---- lab: ULN --------------------------------------------------------
dict(id="h-10", type="LAB_THRESHOLD", trial="NCT07361705",
     text="Blood creatinine ≤ 1.5 x ULN", incl=True,
     patient={"labs": {"CREATININE": (1.65, "mg/dL")}, "uln": {"CREATININE": 1.1}},
     gold="met", tags=["uln", "boundary"], why="1.5 x 1.1 = 1.65 exactly"),
dict(id="h-11", type="LAB_THRESHOLD", trial="NCT07361705",
     text="Blood creatinine ≤ 1.5 x ULN", incl=True,
     patient={"labs": {"CREATININE": (1.66, "mg/dL")}, "uln": {"CREATININE": 1.1}},
     gold="not_met", tags=["uln", "boundary"], why="just over 1.65"),
dict(id="h-12", type="LAB_THRESHOLD", trial="NCT05283330",
     text="Alanine aminotransferase (ALT) and aspartate aminotransferase (AST) "
          "≤3x upper limit of normal (ULN)", incl=True,
     patient={"labs": {"ALT": (60, "U/L"), "AST": (200, "U/L")},
              "uln": {"ALT": 40, "AST": 40}},
     gold="not_met", tags=["uln", "multi_analyte"],
     why="AST 200 > 120; a conjunction fails if either arm fails"),
dict(id="h-13", type="LAB_THRESHOLD", trial="NCT05283330",
     text="Alanine aminotransferase (ALT) and aspartate aminotransferase (AST) "
          "≤3x upper limit of normal (ULN) or ≤ 5 x ULN in the presence of "
          "liver metastases", incl=True,
     patient={"labs": {"ALT": (190, "U/L"), "AST": (190, "U/L")},
              "uln": {"ALT": 40, "AST": 40},
              "conditions": ["LIVER_METASTASES"]},
     gold="met", tags=["uln", "conditional"], why="liver variant 200; both under"),
dict(id="h-14", type="LAB_THRESHOLD", trial="NCT05751798",
     text="hemoglobin ≥ 90 g/L", incl=True, patient={"labs": {}},
     gold="undetermined", tags=["missing_data"], why="not measured"),

# ---- washout: days / weeks -------------------------------------------
dict(id="h-15", type="WASHOUT", trial="NCT06225427",
     text="Received palliative radiation within 7 days of enrollment",
     incl=False, patient={"last_dose": {"RADIOTHERAPY": "2026-08-06"}},
     gold="met", tags=["days"], why="8 days elapsed"),
dict(id="h-16", type="WASHOUT", trial="NCT07241039",
     text="Radiation therapy for central nervous system metastases within "
          "14 days prior to first dose.", incl=False,
     patient={"last_dose": {"RADIOTHERAPY": "2026-08-13"}},
     gold="pending", tags=["days"], expect_date="2026-08-27",
     why="13 Aug + 14 days = 27 Aug"),
dict(id="h-17", type="WASHOUT", trial="NCT07660055",
     text="Use of transfusion support ≤4 weeks prior to imaging agent "
          "administration.", incl=False,
     patient={"last_dose": {"TRANSFUSION": "2026-07-17"}},
     gold="met", tags=["weeks", "boundary"], why="17 Jul + 28 days = 14 Aug"),
dict(id="h-18", type="WASHOUT", trial="NCT06312137",
     text="Has received prior systemic anticancer therapy including "
          "investigational agents within 4 weeks before the first dose",
     incl=False, patient={"last_dose": {"ANTICANCER_THERAPY": "2026-08-05",
                                        "INVESTIGATIONAL": "2026-08-05"}},
     gold="pending", tags=["weeks"], expect_date="2026-09-02",
     why="5 Aug + 28 days = 2 Sep"),

# ---- washout: calendar arithmetic -------------------------------------
dict(id="h-19", type="WASHOUT", trial="NCT06276283",
     text="History of stroke and intracranial hemorrhage within 6 months of "
          "the first dose of study drug.", incl=False,
     patient={"event": {"STROKE": "2026-03-31"}},
     gold="pending", tags=["calendar_month", "month_end"],
     expect_date="2026-09-30", why="31 Mar + 6 months clamps to 30 Sep"),
dict(id="h-20", type="WASHOUT", trial="NCT06276283",
     text="History of stroke and intracranial hemorrhage within 6 months of "
          "the first dose of study drug.", incl=False,
     patient={"event": {"STROKE": "2025-12-31"}},
     gold="met", tags=["calendar_month", "month_end"],
     why="31 Dec 2025 + 6 months = 30 Jun 2026, already past"),
dict(id="h-21", type="WASHOUT", trial="NCT05278052",
     text="Unstable angina and/or congestive heart failure requiring "
          "hospitalization within the last 6 months;", incl=False,
     patient={"event": {"ANGINA": "2026-08-31", "HEART_FAILURE": "2026-08-31"},
              "index": "2027-02-28"},
     gold="met", tags=["calendar_month", "month_end"],
     why="31 Aug 2026 + 6 months clamps to 28 Feb 2027 = index; window closed"),
dict(id="h-22", type="WASHOUT", trial="NCT06218914", index="2024-02-28",
     text="History of clinically significant cardiac disease within the "
          "6 months prior to enrollment", incl=False,
     patient={"event": {"CARDIAC_DISEASE": "2023-08-31"}},
     gold="pending", tags=["calendar_month", "leap", "month_end"],
     expect_date="2024-02-29",
     why="31 Aug 2023 + 6 months clamps to 29 Feb 2024 (2024 is a leap year)"),
dict(id="h-23", type="WASHOUT", trial="NCT05689619",
     text="Diagnosis of any secondary malignancy within the last 3 years",
     incl=False, patient={"event": {"SECOND_MALIGNANCY": "2024-02-29"}},
     gold="pending", tags=["years", "leap"], expect_date="2027-02-28",
     why="29 Feb 2024 + 3 years clamps to 28 Feb 2027"),
dict(id="h-24", type="WASHOUT", trial="NCT05281406",
     text="Osimertinib no longer than 10 weeks before start of chemotherapy "
          "in the treatment phase", incl=False,
     patient={"last_dose": {"EGFR_TKI": "2026-05-01"}},
     gold="met", tags=["weeks"], why="105 days elapsed, past 70"),

# ---- washout: abstention ---------------------------------------------
dict(id="h-25", type="WASHOUT", trial="NCT07241039",
     text="Radiation therapy for central nervous system metastases within "
          "14 days prior to first dose.", incl=False, patient={},
     gold="undetermined", tags=["missing_data"], why="no date, no negative"),
dict(id="h-26", type="WASHOUT", trial="NCT07660055",
     text="Use of transfusion support ≤4 weeks prior to imaging agent "
          "administration.", incl=False, patient={"no_therapy": ["TRANSFUSION"]},
     gold="met", tags=["never_received"], why="never transfused"),

# ---- age --------------------------------------------------------------
dict(id="h-27", type="AGE", trial="NCT05194982",
     text="Age: >=18 years old and <=75 years old (stage Ia); >=18 years old "
          "(stage Ib).", incl=True, patient={"age": 74},
     gold="met", tags=["range"], why="within range"),
dict(id="h-28", type="AGE", trial="NCT05689619", text="≥ 18 - 70 years of age",
     incl=True, patient={"age": 18}, gold="met", tags=["range", "boundary"],
     why="at the floor"),

# ---- prior therapy ----------------------------------------------------
dict(id="h-29", type="PRIOR_THERAPY", trial="NCT05800587",
     text="Participant must have had no more than 3 prior lines of therapy.",
     incl=True, patient={"lines": 1, "complete": True},
     gold="met", tags=["line_count"], why="1 <= 3"),
dict(id="h-30", type="PRIOR_THERAPY", trial="NCT05255302",
     text="Previous treatment with anti-PD-1, anti-PD-L1, Anti-CTLA4 or any "
          "ICI antibody", incl=False,
     patient={"classes": ["CHECKPOINT_INHIBITOR"], "complete": True},
     gold="not_met", tags=["class_presence"], why="has had an ICI"),
dict(id="h-31", type="PRIOR_THERAPY", trial="NCT06481566",
     text="prior use of any EGFR tyrosine kinase inhibitor (EGFR-TKI);",
     incl=False, patient={"classes": ["ALK_TKI"], "complete": True},
     gold="met", tags=["class_presence"],
     why="an ALK TKI is not an EGFR TKI, so the exclusion is not triggered"),
dict(id="h-32", type="PRIOR_THERAPY", trial="NCT07659782",
     text="Have progressed on at least 1 line of prior therapy for locally "
          "advanced/metastatic NSCLC", incl=True,
     patient={"lines": 4, "complete": True, "progressed": True},
     gold="met", tags=["line_count"], why="4 >= 1"),
]
