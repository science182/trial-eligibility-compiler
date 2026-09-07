"""Clinical report -> PatientRecord, with a character span on every field.

Two paths, same output type:

  extract_rules()  deterministic, zero cost, offline. Reuses the vocabularies
                   the compiler already uses -- a report and a criterion speak
                   the same clinical language, so units.py, onco.py,
                   conditions.py and drugs.py all apply unchanged.

  extract_llm()    one model call through llm.py, for prose the rules miss.

`extract()` runs the rules first and asks the model only to fill gaps. The
demo therefore needs no network, and a rate-limit error degrades the result
rather than breaking the page.

Nothing here guesses. A field the report does not state is left None, which the
evaluator surfaces as UNDETERMINED.
"""

import re
from datetime import date, datetime

from conditions import CONDITION_PATTERNS
from drugs import DRUG_CLASS_PATTERNS
from onco import (ALTERATION_PATTERNS, GENE_PATTERNS, HISTOLOGY_PATTERNS,
                  HISTOLOGY_TRAPS, STAGE_VALUES, scan)
from patient import Biomarker, LabValue, PatientRecord, PriorTherapy, Sourced
from units import ANALYTE_PATTERNS, ANALYTE_TRAPS, UnitError, to_canonical

# --------------------------------------------------------------- dates

ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
US = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b")
LONG = re.compile(
    r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+"
    r"(\d{1,2}),?\s+(\d{4})\b", re.I)
MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun",
     "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


def find_dates(text):
    """Every parseable date with its span, left to right."""
    out = []
    for m in ISO.finditer(text):
        try:
            out.append((date(*map(int, m.groups())), m.span()))
        except ValueError:
            pass
    for m in US.finditer(text):
        mo, d, y = map(int, m.groups())
        try:
            out.append((date(y, mo, d), m.span()))
        except ValueError:
            pass
    for m in LONG.finditer(text):
        mo = MONTHS[m.group(1)[:3].lower()]
        try:
            out.append((date(int(m.group(3)), mo, int(m.group(2))), m.span()))
        except ValueError:
            pass
    return sorted(out, key=lambda x: x[1][0])


def _date_near(text, lo, hi):
    """The date whose span falls inside [lo, hi), if any."""
    for d, (s, _) in find_dates(text):
        if lo <= s < hi:
            return d
    return None


# ------------------------------------------------------- demographics

AGE_RE = re.compile(
    r"(\d{1,3})[\s-]*(?:year|yr)[s]?[\s-]*old|\bage[d]?\s*[:=]?\s*(\d{1,3})\b|"
    r"\b(\d{1,3})\s*(?:yo|y/o)\b", re.I)
SEX_RE = re.compile(r"\b(female|male|woman|man)\b", re.I)
ECOG_RE = re.compile(
    r"ECOG(?:\s*(?:PS|performance\s+status|score))?\s*[:=]?\s*(?:of\s+)?([0-4])",
    re.I)
KPS_RE = re.compile(r"(?:Karnofsky|KPS)[^\d]{0,20}(\d{2,3})", re.I)
STAGE_RE = re.compile(r"\bstage\s+(IV|III|II|I)([ABC])?\b", re.I)


def _sourced(text, m, value, group=0):
    return Sourced(value, m.span(group), text[m.start(group):m.end(group)])


# ---------------------------------------------------------------- labs

# "ANC 2.6 x10^9/L", "platelets 187 x10^9/L", "creatinine 0.9 mg/dL"
VALUE_UNIT = re.compile(
    r"[\s:=]*(?:of\s+|was\s+|is\s+)?"
    r"(?P<num>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)\s*"
    r"(?P<unit>x?\s?10\s*\^?\s*\d{1,2}\s*/\s*[a-zA-Z]+|/\s*(?:mm\^?3|uL|µL|L)|"
    r"g\s*/\s*dL|g\s*/\s*L|mg\s*/\s*dL|umol\s*/\s*L|µmol\s*/\s*L|"
    r"mL\s*/\s*min|U\s*/\s*L|IU\s*/\s*L|msec|ms\b|%|mm\s*Hg)?",
    re.I)

ULN_NEAR = re.compile(
    r"(?:institutional\s+)?ULN\s*[:=]?\s*(\d+(?:\.\d+)?)|"
    r"\(\s*(?:ref|normal)[^)]*?(\d+(?:\.\d+)?)\s*\)", re.I)


def extract_labs(text):
    labs = {}
    hits = scan([(n, p) for n, p in ANALYTE_PATTERNS], text)
    for i, (start, end, analyte) in enumerate(hits):
        next_analyte = hits[i + 1][0] if i + 1 < len(hits) else len(text)
        trap = ANALYTE_TRAPS.get(analyte)
        if trap and trap.search(text[max(0, start - 30):end + 30]):
            continue
        if analyte in labs:
            continue
        m = VALUE_UNIT.match(text, end)
        if not m or not m.group("num"):
            continue
        raw = float(m.group("num").replace(",", ""))
        try:
            value, unit = to_canonical(analyte, raw, m.group("unit") or "")
        except UnitError:
            continue

        tail = text[m.end():min(next_analyte, m.end() + 70)]
        u = ULN_NEAR.search(tail)
        uln = float(next(g for g in u.groups() if g)) if u else None

        labs[analyte] = LabValue(
            analyte=analyte, value=value, unit=unit,
            date=_date_near(text, max(0, start - 200), start),
            uln=uln, span=(start, m.end()), text=text[start:m.end()].strip())
    return labs


# ----------------------------------------------------------- biomarkers

BIOMARKER_NEG = re.compile(
    r"\b(?:no|not|negative|absent|wild[\s-]?type|none)\b", re.I)
BIOMARKER_POS = re.compile(
    r"\b(?:detected|positive|present|identified|found|harbou?rs?)\b", re.I)
VAF_RE = re.compile(r"VAF[\s:]*(\d+(?:\.\d+)?)\s*%", re.I)


def extract_biomarkers(text):
    genes = scan(GENE_PATTERNS, text)
    alts = scan(ALTERATION_PATTERNS, text)
    found, tested = [], set()

    for i, (gs, ge, gene) in enumerate(genes):
        tested.add(gene)
        stop = genes[i + 1][0] if i + 1 < len(genes) else len(text)
        window = text[gs:min(stop, gs + 90)]

        own = [a for a in alts if ge <= a[0] < min(stop, ge + 60)]
        # A negation between the gene and the next gene means "not present".
        clause = text[gs:min(stop, gs + 70)]
        negated = bool(BIOMARKER_NEG.search(clause))
        # "ALK, ROS1, BRAF, KRAS: no alterations detected" -- the negation
        # trails a run of genes and governs all of them.
        if not negated and not own:
            after = text[ge:min(len(text), ge + 120)]
            if BIOMARKER_NEG.search(after) and not BIOMARKER_POS.search(
                    text[ge:ge + 40]):
                negated = True
        if negated:
            continue
        if not own:
            continue

        v = VAF_RE.search(window)
        found.append(Biomarker(
            gene=gene, alteration=own[0][2],
            vaf=float(v.group(1)) if v else None,
            span=(gs, own[0][1]), text=text[gs:own[0][1]]))
    return found, tested


# ------------------------------------------------------ prior therapy

LAST_DOSE = re.compile(
    r"last\s+dose[^.\n]{0,30}?(\d{4}-\d{2}-\d{2})|"
    r"(?:through|until|to)\s+(\d{4}-\d{2}-\d{2})", re.I)
PROGRESSED = re.compile(r"progress\w*|\bPD\b|refractory|relapse", re.I)


def extract_therapies(text):
    """(therapies, last_dose_dates, never_received, absence spans).

    A negated run -- "No investigational agent, live vaccine, antibiotics ...
    at any time prior" -- becomes documented absence, not prior therapy.
    """
    therapies, last_dose, never, never_spans = [], {}, set(), {}
    hits = scan([(n, p) for n, p in DRUG_CLASS_PATTERNS], text)
    for i, (s, e, cls) in enumerate(hits):
        if is_negated(text, s, e):
            never.add(cls)
            never_spans.setdefault(f"therapy:{cls}", (s, e))
            continue
        stop = hits[i + 1][0] if i + 1 < len(hits) else len(text)
        window = text[s:min(stop, s + 200)]
        dates = [d for d, _ in find_dates(window)]

        m = LAST_DOSE.search(window)
        end_date = None
        if m:
            iso = m.group(1) or m.group(2)
            end_date = datetime.strptime(iso, "%Y-%m-%d").date()
        elif len(dates) >= 2:
            end_date = max(dates)
        elif dates:
            end_date = dates[0]

        therapies.append(PriorTherapy(
            drug=text[s:e], drug_class=cls,
            start_date=min(dates) if len(dates) >= 2 else None,
            end_date=end_date,
            progressed=True if PROGRESSED.search(window) else None,
            line=i + 1, span=(s, e), text=text[s:e]))
        if end_date and (cls not in last_dose or end_date > last_dose[cls]):
            last_dose[cls] = end_date
    return therapies, last_dose, never, never_spans


# ------------------------------------------------------ comorbidities

NEG_CUE = re.compile(
    r"\b(?:no|not|without|negative\s+for|denies|free\s+of|absent|none)\b", re.I)
# A negation reaches the whole list it introduces: "no pleural or pericardial
# effusion", "No investigational agent, live vaccine, antibiotics ... or
# surgery". Scoping it to the immediately preceding words misses every item
# after the first, which then reads as PRESENT -- the most dangerous possible
# extraction error.
NEG_RESET = re.compile(r"\b(?:but|however|except|although|aside\s+from)\b", re.I)
SENTENCE_END = re.compile(r"[.;\n]")
TRAILING_NEG = re.compile(r"^[\s:,]*(?:is\s+|are\s+|was\s+|were\s+)?"
                          r"(?:negative|absent|not\s+detected|none)\b", re.I)


def _sentence_start(text, pos):
    m = None
    for m2 in SENTENCE_END.finditer(text, 0, pos):
        m = m2
    return m.end() if m else 0


def is_negated(text, start, end):
    """Is the mention at [start, end) under a negation?"""
    lead = text[_sentence_start(text, start):start]
    cue = None
    for m in NEG_CUE.finditer(lead):
        cue = m
    if cue and not NEG_RESET.search(lead[cue.end():]):
        return True
    # "HIV/HBV/HCV negative", "EGFR: not detected"
    return bool(TRAILING_NEG.match(text[end:end + 25]))


def extract_conditions(text):
    """(present, documented-absent, absence spans). Silence appears in none."""
    present, absent, spans = [], set(), {}
    for s, e, cond in scan(CONDITION_PATTERNS, text):
        if is_negated(text, s, e):
            absent.add(cond)
            spans.setdefault(f"comorbidity:{cond}", (s, e))   # first mention
        elif cond not in absent:
            present.append(Sourced(cond, (s, e), text[s:e]))
    # A stated positive outranks a negative for the same code elsewhere in the
    # note: "hypertension, controlled on amlodipine" is a real finding even if
    # a later review of systems says "no hypertension crisis".
    seen = set()
    deduped = []
    for x in present:
        if x.value in seen:
            continue
        seen.add(x.value)
        deduped.append(x)
    survived = absent - seen
    return deduped, survived, {f"comorbidity:{c}": spans[f"comorbidity:{c}"]
                               for c in survived
                               if f"comorbidity:{c}" in spans}


# ------------------------------------------------------------ histology

def extract_histology(text):
    for s, e, code in scan(HISTOLOGY_PATTERNS, text):
        if HISTOLOGY_TRAPS.search(text[max(0, s - 60):e + 40]):
            continue
        if code in ("SOLID_TUMOR",):
            continue
        return Sourced(code, (s, e), text[s:e])
    return None


# ------------------------------------------------------------- driver

def extract_rules(report, index_date=None):
    """Deterministic extraction. No model call, no network, no guessing."""
    text = report
    p = PatientRecord(index_date=index_date or date.today(), report_text=text)

    m = AGE_RE.search(text)
    if m:
        val = next(g for g in m.groups() if g)
        p.age = Sourced(int(val), m.span(), m.group(0))
    m = SEX_RE.search(text)
    if m:
        norm = {"woman": "female", "man": "male"}.get(m.group(1).lower(),
                                                      m.group(1).lower())
        p.sex = Sourced(norm, m.span(), m.group(0))
    m = ECOG_RE.search(text)
    if m:
        p.ecog = Sourced(int(m.group(1)), m.span(), m.group(0))
    m = KPS_RE.search(text)
    if m:
        p.karnofsky = Sourced(int(m.group(1)), m.span(), m.group(0))
    m = STAGE_RE.search(text)
    if m:
        code = (m.group(1) + (m.group(2) or "")).upper()
        if code in STAGE_VALUES:
            p.stage = Sourced(code, m.span(), m.group(0))

    p.histology = extract_histology(text)
    p.labs = extract_labs(text)
    p.biomarkers, p.genes_tested = extract_biomarkers(text)
    p.prior_therapies, p.last_dose_dates, never, never_spans = \
        extract_therapies(text)
    p.comorbidities, p.negative_findings, absent_spans = \
        extract_conditions(text)
    p.negative_findings |= never
    p.negative_spans = {**absent_spans, **never_spans}
    return p


EXTRACTION_PROMPT = """You are extracting structured fields from an oncology \
note for clinical-trial screening.

Return JSON only. For every field, also return the exact verbatim substring of \
the note it came from, so it can be highlighted. If the note does not state a \
field, omit it. Never infer or estimate a value.

Note:
---
{report}
---

JSON keys: age, sex, histology, stage, ecog, biomarkers (list of {{gene, \
alteration, evidence}}), labs (object of analyte -> {{value, unit, evidence}}), \
prior_therapies (list of {{drug, last_dose_date, evidence}}), \
comorbidities_present (list), comorbidities_absent (list)."""


def extract_llm(report, index_date=None):
    """Model-based extraction. Raises LLMUnavailable with no key and no cache."""
    from llm import complete_json
    data = complete_json(EXTRACTION_PROMPT.format(report=report))
    return data


def extract(report, index_date=None, use_llm=False):
    """Rules first; the model only fills what the rules left empty.

    Returns (record, used_llm). Any model failure degrades to the rules result
    rather than propagating -- the demo must render either way.
    """
    rec = extract_rules(report, index_date)
    if not use_llm:
        return rec, False
    try:
        raw = extract_llm(report, index_date)
    except Exception:                                # noqa: BLE001
        return rec, False
    return _merge(rec, raw, report), True


def _merge(rec, raw, report):
    """Fill only gaps. A rule-extracted value is never overwritten by the model."""
    def span_of(snippet):
        if not snippet:
            return None
        i = report.find(snippet)
        return (i, i + len(snippet)) if i >= 0 else None

    if rec.age is None and raw.get("age"):
        rec.age = Sourced(int(raw["age"]), None, None)
    if rec.sex is None and raw.get("sex"):
        rec.sex = Sourced(str(raw["sex"]).lower(), None, None)
    if rec.ecog is None and raw.get("ecog") is not None:
        rec.ecog = Sourced(int(raw["ecog"]), None, None)
    if rec.stage is None and raw.get("stage"):
        code = str(raw["stage"]).upper().replace("STAGE", "").strip()
        if code in STAGE_VALUES:
            rec.stage = Sourced(code, None, None)

    for b in raw.get("biomarkers", []) or []:
        gene = (b.get("gene") or "").upper()
        if gene and gene not in {x.gene for x in rec.biomarkers}:
            rec.biomarkers.append(Biomarker(
                gene=gene, alteration=(b.get("alteration") or "UNKNOWN").upper(),
                span=span_of(b.get("evidence")), text=b.get("evidence")))
            rec.genes_tested.add(gene)

    for cond in raw.get("comorbidities_absent", []) or []:
        rec.negative_findings.add(str(cond).upper().replace(" ", "_"))
    return rec
