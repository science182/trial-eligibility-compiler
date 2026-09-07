"""Criterion text -> typed predicate objects.

One criterion can require several predicates ("AST and ALT <= 2.5 x ULN" is two;
9.1% of hand-read criteria are multi-type), so compile_criterion returns a LIST.

The compiler never decides whether a patient passes. It only records what the
sentence asserts. All comparison, unit conversion, and date arithmetic happen
elsewhere -- conversion here at compile time, comparison in evaluate.py.
"""

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from conditions import (CONDITION_NEGATION, CONDITION_PATTERNS, CONDITION_TRAP,
                        PERMITTED, QUALIFIERS)
from dates import EXACT_UNITS, approx_days, normalize_unit
from drugs import (ANTICANCER_CLASSES, MEASUREMENT_SUBJECT, NOT_A_WASHOUT,
                   NOT_PRIOR_THERAPY_HARD, NOT_PRIOR_THERAPY_SOFT,
                   TREATMENT_DURATION, find_anchor,
                   find_classes, find_events)
from onco import (ALTERATION_PATTERNS, ALTERATION_TRAPS, BIOMARKER_NEGATION,
                  GENE_PATTERNS, GENERIC_ALTERATIONS, HISTOLOGY_EXCLUDED_CUE,
                  HISTOLOGY_PATTERNS,
                  HISTOLOGY_CLAIM_CUE, HISTOLOGY_SUBTYPES, HISTOLOGY_TRAPS,
                  STAGE_DESCRIPTORS, STAGE_RE, STAGE_TOKEN,
                  STAGE_VALUES, expand_stage_range, scan)
from split import NEGATED_INCLUSION
from units import UnitError, clean_unit, find_analyte, to_canonical


class Mutability(Enum):
    IMMUTABLE = "immutable"
    TEMPORAL = "temporal"
    CORRECTABLE = "correctable"
    UNKNOWN = "unknown"


@dataclass
class Criterion:
    trial_id: str
    raw_text: str                 # verbatim source sentence, never discarded
    is_inclusion: bool
    predicate_type: str
    mutability: Mutability
    payload: dict = field(default_factory=dict)
    compiled: bool = False
    start: int = 0                # char offsets into the trial's eligibility block
    end: int = 0

    def to_dict(self):
        d = self.__dict__.copy()
        d["mutability"] = self.mutability.value
        return d


# --------------------------------------------------------------- guards

# Cockcroft-Gault and similar formula prose contains analytes, numbers and
# operators but asserts no threshold. Compiling it produces confident nonsense.
FORMULA_TRAP = re.compile(
    r"140\s*[-‐-―]\s*age|\(\s*140\s*[-‐-―]|"
    r"72\s*[x×*]\s*serum\s+creatinine|multiply\s+above|"
    r"wt\s*\(\s*kg\s*\)|weight\s*\(\s*kg\s*\)\s*[x×*]|"
    r"cr?cl\s*\(?\s*ml/min\s*\)?\s*=|equation\s+should\s+be\s+used",
    re.I,
)

# Units that mean this number is a duration, a dose, or a grade -- not a lab value.
NON_LAB_UNIT = re.compile(
    r"^(?:days?|weeks?|months?|years?|hours?|hrs?|half[\s-]?li(?:fe|ves)|"
    r"cycles?|doses?|lines?|mg/day|mg|g/day|gy|cm|mm(?!3)|kg|bpm|packs?)$",
    re.I,
)

# A scale word right after the operator means grade/stage/class, not a lab.
SCALE_AFTER_OP = re.compile(
    r"^\s*(?:grade|stage|class|ecog|ps\b|nyha|child[\s-]?pugh|level)\b", re.I
)

OPERATORS = {
    ">=": ">=", "=>": ">=", "≥": ">=", "≧": ">=",
    "<=": "<=", "=<": "<=", "≤": "<=", "≦": "<=",
    ">": ">", "<": "<",
    "at least": ">=", "no less than": ">=", "not less than": ">=",
    "greater than or equal to": ">=", "equal to or greater than": ">=",
    "less than or equal to": "<=", "equal to or less than": "<=",
    "no more than": "<=", "not more than": "<=", "not exceed": "<=",
    "not exceeding": "<=", "at most": "<=", "up to": "<=",
    "greater than": ">", "more than": ">", "above": ">", "over": ">",
    "less than": "<", "below": "<", "under": "<",
}

# Symbol operators need no word boundary -- registry text writes "ALT<= 2.5 x ULN"
# with no space, and a \w lookbehind would silently drop every such threshold.
# Word operators do need boundaries so "above" does not fire inside "aboveground".
_SYM = [k for k in OPERATORS if not k[0].isalpha()]
_WORD = [k for k in OPERATORS if k[0].isalpha()]
_SYM_ALT = "|".join(sorted((re.escape(k) for k in _SYM), key=len, reverse=True))
_WORD_ALT = "|".join(sorted((re.escape(k) for k in _WORD), key=len, reverse=True))
OP_RE = re.compile(rf"({_SYM_ALT})|\b({_WORD_ALT})\b", re.I)

UNIT_ALT = (
    r"10\s*\^?\s*\d{1,2}\s*/\s*(?:L|l|uL|µL|μL|mm3|mm\^?3)"
    r"|x?10\s*\^?\s*\d{1,2}\s*/\s*(?:L|l|uL|µL|μL|mm3|mm\^?3)"
    r"|cells?\s*/\s*(?:mm\^?3|uL|µL|μL|L)"
    r"|/\s*(?:mm\^?3|uL|µL|μL|cumm|cmm|L)"
    r"|g\s*/\s*dL|g\s*/\s*L|mg\s*/\s*dL|mg\s*/\s*L"
    r"|umol\s*/\s*L|µmol\s*/\s*L|μmol\s*/\s*L|mmol\s*/\s*L"
    r"|mL\s*/\s*min\s*/\s*1\.73\s*m\s*\^?2|mL\s*/\s*min|ml\s*/\s*min"
    r"|U\s*/\s*L|IU\s*/\s*L|msec|ms\b|sec\b|seconds?|%"
    r"|mm\s*Hg|kg\s*/\s*m\s*\^?2"
)

# "BP >= 150 mm Hg systolic" names the half AFTER the number.
BP_QUALIFIER = re.compile(r"^\s*(?:mm\s*Hg\s*)?(systolic|diastolic)", re.I)

ULN_ALT = (
    r"upper\s+limits?\s+of\s+normal|lower\s+limits?\s+of\s+normal"
    r"|institutional\s+upper\s+limit[s]?\s+of\s+normal"
    r"|ULN|UNL|LLN|LNL"
)

NUM = r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?|\.\d+"

# Filler between the multiplier and the reference word: "1.5 x THE upper limit
# of normal", "1.5 x INSTITUTIONAL ULN". Without this the number parses as an
# absolute value and "bilirubin <= 1.5 x ULN" silently becomes 1.5 mg/dL.
REF_FILLER = r"(?:the|institutional|local|site|laboratory|lab|study|central)\s+"

TAIL_RE = re.compile(
    rf"""^\s*(?:or\s+equal\s+to\s+)?
        (?:
            (?P<num>{NUM})
            \s*(?:[x×*]|times)?\s*(?:{REF_FILLER})*
            (?:(?P<uln>{ULN_ALT})|(?P<unit>{UNIT_ALT}))?
          |
            (?:{REF_FILLER})*(?P<ulnonly>{ULN_ALT})
        )
    """,
    re.I | re.X | re.VERBOSE,
)

# Conditions that select between alternative thresholds in the same sentence.
# Negated forms are tested first: "no liver involvement" also matches the
# affirmative pattern, so order is load-bearing.
CONDITIONS = [
    ("no_liver_metastases",
     r"n[o']?\s*(?:demonstrable\s+)?(?:liver|hepatic)|without\s+(?:liver|hepatic)|"
     r"absence\s+of\s+(?:liver|hepatic)"),
    ("liver_metastases",
     r"liver\s+(?:metastas|involve|invasion|lesion)|hepatic\s+metastas|"
     r"hepatocellular|with\s+liver"),
    ("gilberts", r"gilbert"),
]


def _normalize(text):
    """Undo registry markdown escaping and unicode so the regexes see plain ASCII ops."""
    t = text
    t = t.replace("\\<", "<").replace("\\>", ">").replace("\\=", "=")
    t = t.replace("\\^", "^").replace("\\[", "[").replace("\\]", "]")
    t = t.replace("＜", "<").replace("＞", ">")   # fullwidth < >
    t = t.replace("，", ",").replace("；", ";")   # fullwidth , ;
    t = t.replace("（", "(").replace("）", ")")
    t = t.translate(str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹",
                                  "0123456789"))
    return t


def _parse_number(s):
    s = s.replace(",", "")
    return float(s)


def _match_condition(window):
    for name, pat in CONDITIONS:
        if re.search(pat, window, re.I):
            return name
    return None


# Alternation boundaries. A condition binds within its own clause, so the text
# is cut at these before conditions are matched. "if" and "with" are NOT
# boundaries -- they introduce the qualifier that belongs to the clause it is in
# ("<= 2.5 x ULN if no liver involvement | or | <= 5 x ULN with liver mets").
# The period must be a sentence break, not the decimal point in "2.5 x ULN".
CLAUSE_SPLIT = re.compile(r"\bor\b|\bunless\b|\bexcept\b|\.(?=\s|$)|[;()]", re.I)


def _assign_conditions(text, thresholds):
    """Map each threshold to the condition governing it.

    Four shapes occur in registry text and all reduce to the same rule once the
    sentence is cut into clauses -- a condition binds the thresholds in its own
    clause, and a clause carrying a condition but no threshold of its own binds
    forward to the next clause that has one:

      "<= 2.5 x ULN (<= 5 x ULN in case of liver mets)"     own clause
      "<= 2.5 x ULN if no liver | or | <= 5 x ULN with liver"  own clause, each
      "<= 1.5 x ULN. For subjects with Gilbert's, <= 3 mg/dL"  carried forward
      "<= 1.5 x ULN unless Gilbert's, then <= 3 mg/dL"         carried forward
    """
    bounds = [0] + [m.end() for m in CLAUSE_SPLIT.finditer(text)] + [len(text)]
    spans = [(bounds[i], bounds[i + 1]) for i in range(len(bounds) - 1)]

    out = {}
    pending = None
    for lo, hi in spans:
        seg = text[lo:hi]
        seg_cond = _match_condition(seg)
        seg_thrs = [t for t in thresholds if lo <= t["start"] < hi]
        if seg_thrs:
            cond = seg_cond or pending
            for t in seg_thrs:
                out[t["start"]] = cond
            pending = None
        elif seg_cond:
            pending = seg_cond
    return out


def _scan_thresholds(text):
    """Yield dicts describing every threshold expression in `text`."""
    out = []
    for m in OP_RE.finditer(text):
        op_raw = (m.group(1) or m.group(2)).lower()
        op = OPERATORS[op_raw]
        tail = text[m.end():m.end() + 60]

        if SCALE_AFTER_OP.match(tail):
            continue

        tm = TAIL_RE.match(tail)
        if not tm:
            continue

        if tm.group("ulnonly"):
            value, unit, basis = 1.0, None, _basis(tm.group("ulnonly"))
        else:
            if not tm.group("num"):
                continue
            value = _parse_number(tm.group("num"))
            if tm.group("uln"):
                unit, basis = None, _basis(tm.group("uln"))
            else:
                unit = (tm.group("unit") or "").strip()
                basis = "absolute"
                if unit and NON_LAB_UNIT.match(clean_unit(unit)):
                    continue
                # a bare number followed by a duration word is a washout, not a lab
                after = tail[tm.end():tm.end() + 14]
                if re.match(r"\s*(?:days?|weeks?|months?|years?|hours?|"
                            r"half[\s-]?li)", after, re.I):
                    continue

        out.append({
            "op": op,
            "value": value,
            "unit": unit,
            "basis": basis,
            "start": m.start(),
            "end": m.end() + (tm.end() if tm else 0),
        })
    return out


def _basis(token):
    return "lln" if re.search(r"LLN|LNL|lower", token, re.I) else "uln"


def _scan_analytes(text):
    """All analyte mentions with positions, left to right."""
    from units import ANALYTE_PATTERNS, ANALYTE_TRAPS

    hits = []
    for name, pat in ANALYTE_PATTERNS:
        trap = ANALYTE_TRAPS.get(name)
        if trap and trap.search(text):
            continue
        for m in re.finditer(pat, text, re.I):
            hits.append((m.start(), m.end(), name))
    hits.sort()

    # Drop mentions swallowed by a longer overlapping one
    # ("creatinine" inside "creatinine clearance").
    kept = []
    for s, e, n in hits:
        if kept and s < kept[-1][1]:
            if (e - s) > (kept[-1][1] - kept[-1][0]):
                kept[-1] = (s, e, n)
            continue
        # "International Normalized Ratio (INR)" is ONE analyte, not two.
        # Left as two hits it breaks conjunction grouping: the gap between the
        # long form and its own abbreviation contains no "or", so "INR or PT"
        # would be read as a conjunction.
        if kept and kept[-1][2] == n and s - kept[-1][1] <= 3:
            kept[-1] = (kept[-1][0], e, n)
            continue
        kept.append((s, e, n))
    return kept


# A bare threshold with no analyte of its own restates or qualifies the previous
# one ("ANC >= 1500/mm3 or >= 1.5 x 10^9/L", "AST <= 2.5 x ULN (<= 5 x ULN if
# liver mets)", "<= 1.5 x ULN unless Gilbert's, then <= 3 mg/dL"). Inheritance is
# blocked only by a clause break, which would mean a new subject.
CLAUSE_BREAK = re.compile(r";|\.\s+[A-Z]|\bfor\s+(?:patients|subjects)\b", re.I)
# "or" between two bound thresholds makes them alternatives, not both-required.
CONNECTOR_DISJUNCT = re.compile(r"\bor\b", re.I)


def compile_lab_thresholds(text):
    """Extract LAB_THRESHOLD payloads from one criterion. May return several."""
    t = _normalize(text)

    # A trailing Cockcroft-Gault definition must not void the real thresholds
    # that precede it ("CrCl >= 30 mL/min. For estimation, the C-G equation
    # should be used: ..."). Cut the formula off and compile what came before.
    fm = FORMULA_TRAP.search(t)
    if fm:
        t = t[:fm.start()]
        if not t.strip():
            return []

    analytes = _scan_analytes(t)
    thresholds = _scan_thresholds(t)
    if not analytes or not thresholds:
        return []

    conditions = _assign_conditions(t, thresholds)

    events = [(s, "a", (s, e, n)) for s, e, n in analytes]
    events += [(d["start"], "t", d) for d in thresholds]
    events.sort(key=lambda x: (x[0], x[1] == "t"))

    payloads = []
    pending, last_bound = [], []
    group = 0
    prev_thr_end = None

    for _, kind, data in events:
        if kind == "a":
            pending.append(data)          # (start, end, analyte)
            continue

        thr = data
        if pending:
            first_analyte_at = pending[0][0]
            if prev_thr_end is not None:
                # Same group only when the two are explicit alternatives.
                gap = t[prev_thr_end:first_analyte_at]
                if not CONNECTOR_DISJUNCT.search(gap):
                    group += 1
            # Analytes sharing one threshold are joined by AND far more often
            # than OR -- "AST and ALT <= 3 x ULN" requires BOTH. Giving them a
            # single group would OR them, so a passing AST would mask a failing
            # ALT. Only an explicit "or" between them shares a group.
            bound = []
            for i, (a_s, a_e, name) in enumerate(pending):
                if i and not CONNECTOR_DISJUNCT.search(t[pending[i - 1][1]:a_s]):
                    group += 1
                bound.append((name, group))
            pending = []
        else:
            gap = t[prev_thr_end:thr["start"]] if prev_thr_end is not None else ""
            if last_bound and len(gap) < 90 and not CLAUSE_BREAK.search(gap):
                bound = last_bound
            else:
                prev_thr_end = thr["end"]
                continue

        last_bound = bound
        cond = conditions.get(thr["start"])
        prev_thr_end = thr["end"]

        for analyte, grp in bound:
            if analyte == "BLOOD_PRESSURE":
                q = BP_QUALIFIER.match(t[thr["end"]:thr["end"] + 24])
                if q:
                    analyte = "BP_" + q.group(1).upper()
            p = {
                "analyte": analyte,
                "operator": thr["op"],
                "basis": thr["basis"],
                "raw_value": thr["value"],
                "raw_unit": thr["unit"],
                "condition": cond,
                "group": grp,
            }
            if thr["basis"] == "absolute":
                try:
                    val, unit = to_canonical(analyte, thr["value"], thr["unit"])
                except UnitError:
                    continue          # abstain rather than guess a unit
                p["value"], p["unit"] = val, unit
            else:
                # value is a multiple of the reference limit; resolved at eval
                p["value"], p["unit"] = thr["value"], thr["basis"].upper()
            payloads.append(p)

    # Dedupe identical predicates (dual-unit restatements collapse here).
    seen, unique = set(), []
    for p in payloads:
        key = (p["analyte"], p["operator"], p["value"], p["unit"],
               p["basis"], p["condition"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(p)
    return unique


# =====================================================================
# WASHOUT
# =====================================================================

TIME_UNIT = r"days?|weeks?|months?|years?|hours?|hrs?|wks?|mos?|yrs?"

# "within 4 weeks", "at least 6 months", ">= 42 days", "4-12 weeks", "1 month"
DURATION_RE = re.compile(
    rf"""(?P<lo>\d+(?:\.\d+)?)\s*(?:-|to|–|—|or)\s*(?P<hi>\d+(?:\.\d+)?)\s*
         (?P<unit_range>{TIME_UNIT})\b
       | (?P<amount>\d+(?:\.\d+)?)\s*(?P<unit>{TIME_UNIT})\b
       | (?P<worded>one|two|three|four|five|six|twelve)\s+(?P<unit_word>{TIME_UNIT})\b
       | (?:last|past|previous|preceding)\s+(?P<unit_bare>{TIME_UNIT})\b
    """,
    re.I | re.X,
)

WORDED = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
          "twelve": 12}

HALF_LIFE_RE = re.compile(r"(\d+)\s*half[\s-]?li(?:fe|ves)", re.I)
WHICHEVER_RE = re.compile(r"whichever\s+is\s+(longer|shorter)", re.I)

# A duration only defines a washout when a marker introduces or follows it.
# Without one the number is a dose schedule, a treatment duration, or prose.
# The marker may PRECEDE the duration ("within 4 weeks") or FOLLOW it
# ("surgery 4-12 weeks prior to enrollment"), so both sides are checked.
WINDOW_MARKER_BEFORE = re.compile(
    r"(?:within|in\s+the\s+(?:last|past|previous)|over\s+the\s+(?:last|past)|"
    r"during\s+the\s+(?:last|past)|at\s+least|no\s+less\s+than|minimum\s+of|"
    r"for\s+at\s+least|elapsed|since|prior\s+to|before|after|"
    # NOTE: bare "completed"/"received"/"treated" are deliberately absent. They
    # introduce treatment DURATIONS as often as windows ("completed 3 years
    # adjuvant osimertinib", "12 weeks on continued pembrolizumab"), which are
    # not washouts.
    r"completed\s+at\s+least|free\s+of|stable\s+for|interval\s+of|"
    r"discontinued\s+(?:for|at\s+least)|less\s+than|[≥>]=?)"
    # Punctuation and inline operators may sit between the marker and the
    # number: "within (<=) 365 days".
    r"[\s(\[]*(?:the\s+)?[≥≤<>=]*[\s)\]]*$",
    re.I,
)
WINDOW_MARKER_AFTER = re.compile(
    r"^\s*(?:prior\s+to|before|preceding|ahead\s+of|of\s+the\s+first|"
    r"must\s+have\s+elapsed|have\s+elapsed|elapsed|since|from\s+the\s+last|"
    r"interval|whichever)",
    re.I,
)

# Windows that run FORWARD from the anchor (obligations after the last dose)
# rather than backward into the patient's history.
FORWARD_WINDOW = re.compile(
    r"\b(?:following|after)\s+the\s+last\s+(?:dose|administration)|"
    r"until\s+\d+|post[\s-]treatment\s+for", re.I
)

MAX_WINDOW_DAYS = 365 * 10


def _scan_durations(text):
    """Yield window dicts for every duration introduced by a window marker."""
    out = []
    for m in DURATION_RE.finditer(text):
        if m.group("unit_range"):
            # "4-12 weeks prior to enrollment": the binding edge is the longer
            # one -- the patient is ineligible until the wider window closes.
            amount = max(float(m.group("lo")), float(m.group("hi")))
            unit = m.group("unit_range")
        elif m.group("amount"):
            amount, unit = float(m.group("amount")), m.group("unit")
        elif m.group("worded"):
            amount = WORDED[m.group("worded").lower()]
            unit = m.group("unit_word")
        else:
            # "within the past month", "in the previous year" -- an unstated
            # count of one.
            amount, unit = 1, m.group("unit_bare")

        # "past/previous/last <unit>" is its own marker; everything else needs
        # one on the left ("within 4 weeks") or the right ("4 weeks prior to").
        if not m.group("unit_bare"):
            before = text[max(0, m.start() - 40):m.start()]
            after = text[m.end():m.end() + 30]
            if not (WINDOW_MARKER_BEFORE.search(before)
                    or WINDOW_MARKER_AFTER.match(after)):
                continue

        try:
            days = approx_days(amount, unit)
        except KeyError:
            continue
        if days <= 0 or days > MAX_WINDOW_DAYS:
            continue

        out.append({
            "amount": amount,
            "unit": normalize_unit(unit),
            "days": days,
            "start": m.start(),
            "end": m.end(),
        })
    return out


def compile_washouts(text, context=()):
    """Extract WASHOUT payloads from one criterion.

    `context` holds ancestor list headers. A parent frequently carries the
    window for its children ("Any of the following within 6 months before the
    first dose:" / "unstable angina pectoris"), so when the criterion states no
    window of its own the parent's is inherited.
    """
    t = _normalize(text)
    if NOT_A_WASHOUT.search(t):
        return []

    windows = _scan_durations(t)
    inherited = False
    if not windows and context:
        ctx = _normalize(" ".join(context))
        if not NOT_A_WASHOUT.search(ctx):
            windows = _scan_durations(ctx)
            inherited = True
            if windows:
                windows = [dict(w, start=0, end=0) for w in windows]

    if not windows:
        return []

    subjects = [(s, e, n, "therapy") for s, e, n in find_classes(t)]
    subjects += [(s, e, n, "event") for s, e, n in find_events(t)]
    subjects.sort()
    if not subjects:
        return []

    hl = HALF_LIFE_RE.search(t)
    wh = WHICHEVER_RE.search(t)

    def bind(subject_list, w):
        out_ = []
        for s_start, s_end, name, kind in subject_list:
            # "Hb > 9.0 g/dL (within 28 days prior to randomization)" is a
            # recency window on a measurement, not a washout.
            span = t[s_end:w["start"]] if s_end <= w["start"] else ""
            if MEASUREMENT_SUBJECT.search(span) or MEASUREMENT_SUBJECT.search(
                    t[max(0, w["start"] - 30):w["start"]]):
                continue
            anchor, inferred = find_anchor(t, w["end"])
            out_.append({
                "drug_or_class": name,
                "subject_kind": kind,
                "days": w["days"],
                "amount": w["amount"],
                "unit": w["unit"],
                "exact": w["unit"] in EXACT_UNITS,
                "anchor_event": anchor,
                "anchor_inferred": inferred,
                "half_lives": int(hl.group(1)) if hl else None,
                "whichever": wh.group(1).lower() if wh else None,
                "window_from_context": inherited,
            })
        return out_

    payloads = []

    # A window inherited from a parent header governs every subject named in
    # the child ("Any of the following within 6 months:" / "stroke ... MI").
    if inherited:
        for w in windows:
            payloads += bind(subjects, w)
        return _dedupe_washouts(payloads)

    # Otherwise walk subjects and windows in order, binding every subject
    # accumulated since the previous window -- "corticosteroids or other
    # immunosuppressive therapy within 2 weeks" governs both.
    events = [(s[0], "s", s) for s in subjects]
    events += [(w["start"], "w", w) for w in windows]
    events.sort(key=lambda x: (x[0], x[1] == "w"))

    pending, last_bound = [], []
    for _, kind, data in events:
        if kind == "s":
            pending.append(data)
            continue
        w = data
        after = t[w["end"]:w["end"] + 45]
        if FORWARD_WINDOW.search(after) or TREATMENT_DURATION.match(after):
            pending = []
            continue
        if pending:
            bound, pending = pending, []
        elif last_bound:
            bound = last_bound          # "within 28 days or 5 half-lives"
        else:
            # Window stated before its subject: ">= 6 months since
            # discontinuation of adjuvant osimertinib".
            ahead = [s for s in subjects if s[0] > w["end"]]
            if not ahead:
                continue
            bound = [ahead[0]]
        last_bound = bound
        payloads += bind(bound, w)

    return _dedupe_washouts(payloads)


def _dedupe_washouts(payloads):
    """Collapse restatements of the same window on the same class."""
    seen, unique = set(), []
    for p in payloads:
        key = (p["drug_or_class"], p["days"], p["anchor_event"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(p)
    return unique


# =====================================================================
# AGE
# =====================================================================

AGE_CUE = re.compile(
    r"\bages?d?\b|\byears?\s+(?:of\s+age|old)\b|\byo\b", re.I)

# "reproductive age", "childbearing age", and the Cockcroft-Gault "(140 - age)"
# all contain the word but state no age limit.
AGE_TRAP = re.compile(
    r"reproductive\s+age|childbearing\s+age|age\s+of\s+childbearing|"
    r"140\s*[-‐-―]\s*age|\(\s*140|bone\s+age|gestational", re.I)

# "Age >= 18 years", "aged 18 >= years" (operator misplaced), "Age: >= 18"
AGE_BOUND_RE = re.compile(
    rf"(?:(?P<op1>{_SYM_ALT}|at\s+least|no\s+less\s+than|older\s+than|"
    rf"greater\s+than|younger\s+than|less\s+than|no\s+older\s+than|"
    rf"up\s+to|between|from)\s*(?P<num1>\d{{1,3}})"
    rf"|(?P<num2>\d{{1,3}})\s*(?P<op2>{_SYM_ALT})"
    rf"|(?P<num3>\d{{1,3}})\s*(?:years?\s+(?:old\s+|of\s+age\s+)?or\s+"
    rf"(?P<dir>older|above|greater|younger|less)))",
    re.I,
)

AGE_MIN_OPS = {">=", ">", "at least", "no less than", "older than",
               "greater than", "between", "from"}
AGE_MAX_OPS = {"<=", "<", "younger than", "less than", "no older than",
               "up to"}


def compile_age(text):
    """Extract an AGE payload. At most one per criterion."""
    t = _normalize(text)
    if not AGE_CUE.search(t) or AGE_TRAP.search(t):
        return []

    lo = hi = None
    for m in AGE_BOUND_RE.finditer(t):
        if m.group("num3"):
            n = int(m.group("num3"))
            if m.group("dir").lower() in {"older", "above", "greater"}:
                lo = n if lo is None else min(lo, n)
            else:
                hi = n if hi is None else max(hi, n)
            continue

        op = (m.group("op1") or m.group("op2") or "").lower().strip()
        n = int(m.group("num1") or m.group("num2"))
        if not 0 < n <= 120:
            continue
        canon = OPERATORS.get(op, op)
        if canon in AGE_MIN_OPS:
            lo = n if lo is None else min(lo, n)
        elif canon in AGE_MAX_OPS:
            hi = n if hi is None else max(hi, n)

    # "Age from 18 to 80", "Between the ages of 18 and 75", ">= 18 - 70 years"
    span = re.search(r"(?:between|from|ages?\s+of)\s+(\d{1,3})\s*"
                     r"(?:-|to|and|–)\s*(\d{1,3})", t, re.I) or re.search(
        r"(\d{1,3})\s*[-–]\s*(\d{1,3})\s*years?\s*(?:of\s+age|old)", t, re.I)
    if span:
        a, b = int(span.group(1)), int(span.group(2))
        if 0 < a < b <= 120:
            lo, hi = a, b

    if lo is None and hi is None:
        return []
    if lo is not None and hi is not None and lo > hi:
        return []
    return [{"min_years": lo, "max_years": hi}]


# =====================================================================
# PERFORMANCE_STATUS
# =====================================================================

PS_SCALES = [
    ("ECOG", r"\bECOG\b|eastern\s+cooperative\s+oncology\s+group|\bZubrod\b|"
             r"\bWHO\s+performance\b"),
    ("KARNOFSKY", r"\bKarnofsky\b|\bKPS\b"),
    ("ASA", r"american\s+society\s+of\s+anesthesiologists|\bASA\b"),
    ("LANSKY", r"\bLansky\b"),
]
PS_CUE = re.compile(r"performance\s+(?:status|score)|\bECOG\b|\bKarnofsky\b|"
                    r"\bKPS\b|\bPS\s*[0-4]|functional\s+status|"
                    r"physical\s+status|\bASA\b", re.I)

# ECOG 0-4, Karnofsky 0-100 in tens, ASA in roman numerals.
PS_RANGE_RE = re.compile(r"\b([0-4])\s*(?:-|to|–|or|,)\s*([0-4])\b")
PS_SINGLE_RE = re.compile(r"\b([0-4])\b")
PS_OP_RE = re.compile(rf"({_SYM_ALT}|at\s+least|no\s+more\s+than|"
                      rf"greater\s+than|less\s+than)\s*(\d{{1,3}})", re.I)
ASA_RE = re.compile(r"\b(I{1,3}V?|IV)\s*(?:-|to|–)\s*(I{1,3}V?|IV)\b")


def compile_performance_status(text):
    t = _normalize(text)
    if not PS_CUE.search(t):
        return []

    scale = None
    for name, pat in PS_SCALES:
        if re.search(pat, t, re.I):
            scale = name
            break
    if scale is None:
        return []

    if scale == "ASA":
        m = ASA_RE.search(t)
        if not m:
            return []
        roman = {"I": 1, "II": 2, "III": 3, "IV": 4}
        a, b = roman.get(m.group(1).upper()), roman.get(m.group(2).upper())
        if a is None or b is None:
            return []
        return [{"scale": "ASA", "min_value": min(a, b), "max_value": max(a, b),
                 "operator": None, "value": None}]

    # Search after the scale name so "within 7 days" and stray digits elsewhere
    # in the sentence do not supply the value.
    m_scale = re.search(dict(PS_SCALES)[scale], t, re.I)
    tail = t[m_scale.end():m_scale.end() + 60]

    if scale == "KARNOFSKY":
        op = PS_OP_RE.search(tail)
        if not op:
            return []
        canon = OPERATORS.get(op.group(1).lower().strip(), op.group(1))
        v = int(op.group(2))
        if not 0 <= v <= 100:
            return []
        if canon in {">=", ">", "at least"}:
            return [{"scale": "KARNOFSKY", "min_value": v, "max_value": None,
                     "operator": canon, "value": v}]
        return [{"scale": "KARNOFSKY", "min_value": None, "max_value": v,
                 "operator": canon, "value": v}]

    # The value usually follows the scale name, but not always: "Have a
    # performance status of 0 on the ECOG Performance Status".
    lead = t[max(0, m_scale.start() - 45):m_scale.start()]

    rng = PS_RANGE_RE.search(tail) or PS_RANGE_RE.search(lead)
    if rng:
        a, b = int(rng.group(1)), int(rng.group(2))
        return [{"scale": scale, "min_value": min(a, b), "max_value": max(a, b),
                 "operator": None, "value": None}]

    op = PS_OP_RE.search(tail)
    if op:
        canon = OPERATORS.get(op.group(1).lower().strip(), op.group(1))
        v = int(op.group(2))
        if not 0 <= v <= 4:
            return []
        if canon in {"<=", "<"}:
            return [{"scale": scale, "min_value": 0,
                     "max_value": v if canon == "<=" else v - 1,
                     "operator": canon, "value": v}]
        return [{"scale": scale, "min_value": None, "max_value": None,
                 "operator": canon, "value": v}]

    single = PS_SINGLE_RE.search(tail) or PS_SINGLE_RE.search(lead)
    if single:
        v = int(single.group(1))
        return [{"scale": scale, "min_value": v, "max_value": v,
                 "operator": None, "value": None}]
    return []


# =====================================================================
# HISTOLOGY
# =====================================================================

def compile_histology(text):
    t = _normalize(text)
    hits = scan(HISTOLOGY_PATTERNS, t)
    if not hits:
        return []

    allowed, excluded = [], []
    for s, e, code in hits:
        # A carve-out ("adequately treated squamous cell skin cancer") or a
        # sibling disease in a basket trial says nothing about this tumour.
        window = t[max(0, s - 60):min(len(t), e + 40)]
        if HISTOLOGY_TRAPS.search(window):
            continue
        # First mention decides. "NSCLC with mixed SCLC" excludes the mixed
        # component, not NSCLC, even though NSCLC is restated after the cue.
        if code in allowed or code in excluded:
            continue
        # A generic term ("NSCLC", "solid tumor") is background unless the
        # sentence actually claims a diagnosis; a subtype is always a claim.
        # The cue can sit well before the term ("Pathologically proven
        # diagnosis of non-operable stage IIB or III ... NSCLC") or after it
        # ("NSCLC confirmed by histopathology"), so both sides are checked.
        if code not in HISTOLOGY_SUBTYPES and not (
                HISTOLOGY_CLAIM_CUE.search(t[max(0, s - 140):s])
                or HISTOLOGY_CLAIM_CUE.search(t[e:e + 60])):
            continue
        # The exclusion cue must be in the term's OWN clause. Looking back a
        # fixed span lets "mixed" from an earlier clause mark a later,
        # unrelated mention as excluded.
        cue = t[max(0, s - 45):s]
        boundary = max(cue.rfind(","), cue.rfind(";"), cue.rfind(")"),
                       cue.rfind("("))
        for m_or in re.finditer(r"\bor\b", cue, re.I):
            boundary = max(boundary, m_or.end())
        if boundary >= 0:
            cue = cue[boundary:]
        if HISTOLOGY_EXCLUDED_CUE.search(cue) or code in {"SCLC", "LCNEC"}:
            excluded.append(code)
        else:
            allowed.append(code)

    if not allowed and not excluded:
        return []
    return [{"allowed_codes": allowed, "excluded_codes": excluded}]


# =====================================================================
# STAGE
# =====================================================================

STAGE_CUE = re.compile(r"\bstag(?:e|es|ing)\b|\bmetastatic\b|"
                       r"locally[\s-]advanced|\bAJCC\b|\bTNM\b|\bUICC\b", re.I)
# "Stage" must be nearby or the roman numerals are section numbering.
STAGE_NEAR = 40

# "prior systemic treatment FOR stage IIIB/IV NSCLC" describes what the patient
# was treated for, not the stage this trial admits.
STAGE_AS_THERAPY_CONTEXT = re.compile(
    r"(?:therapy|treatment|treated|radiotherapy|chemo\w*|immunotherapy|"
    r"regimens?|lines?)\s+(?:\w+\s+){0,3}?for\s*$", re.I)


def compile_stage(text):
    t = _normalize(text)
    if not STAGE_CUE.search(t):
        return []

    allowed, from_desc = [], False

    for m in re.finditer(r"\bstages?\b", t, re.I):
        if STAGE_AS_THERAPY_CONTEXT.search(t[max(0, m.start() - 60):m.start()]):
            continue
        seg = t[m.end():m.end() + STAGE_NEAR]
        toks = [x.group(1).upper() for x in STAGE_RE.finditer(seg)]
        toks = [x for x in toks if x in STAGE_VALUES]
        if not toks:
            continue
        rng = re.search(rf"({STAGE_TOKEN})\s*(?:-|to|–|through)\s*({STAGE_TOKEN})",
                        seg)
        if rng and rng.group(1).upper() in STAGE_VALUES \
                and rng.group(2).upper() in STAGE_VALUES:
            allowed += expand_stage_range(rng.group(1).upper(),
                                          rng.group(2).upper())
        else:
            allowed += toks

    if not allowed:
        for name, codes, pat in STAGE_DESCRIPTORS:
            if re.search(pat, t, re.I):
                allowed += sorted(codes, key=lambda c: STAGE_VALUES[c])
                from_desc = True

    if not allowed:
        return []
    uniq = sorted(set(allowed), key=lambda c: STAGE_VALUES[c])
    return [{"allowed_stages": uniq, "from_descriptor": from_desc}]


# =====================================================================
# BIOMARKER
# =====================================================================

def compile_biomarkers(text):
    t = _normalize(text)
    genes = scan(GENE_PATTERNS, t)
    if not genes:
        return []
    if ALTERATION_TRAPS.search(t):
        return []

    alterations = scan(ALTERATION_PATTERNS, t)
    payloads = []
    for i, (g_start, g_end, gene) in enumerate(genes):
        # A gene's alterations end where the next gene begins, so "KRAS G12C
        # ... EGFR L858R" cannot cross-assign.
        stop = genes[i + 1][0] if i + 1 < len(genes) else len(t)
        own = [a for a in alterations
               if g_end <= a[0] < min(stop, g_end + 60)]

        # A gene list shares one trailing alteration: "EGFR, ALK, ROS1, MET or
        # RET mutations/fusions".
        if not own:
            last_gene_end = genes[-1][1]
            own = [a for a in alterations
                   if last_gene_end <= a[0] < last_gene_end + 60]
        if not own:
            own = [a for a in alterations
                   if a[1] <= g_start and g_start - a[1] < 30][-1:]
        if not own:
            continue

        # "EGFR sensitizing mutations (Exon19del and/or L858R)": the specific
        # alterations are the claim; "mutations" is just the noun.
        specific = [a for a in own if a[2] not in GENERIC_ALTERATIONS]
        alts = [a[2] for a in specific] if specific else [own[0][2]]

        # Negation is looked for in the clause, not the whole sentence, so a
        # trailing carve-out cannot flip an earlier requirement.
        lo = max(0, g_start - 70)
        clause = t[lo:g_end + 30]
        cut = max(clause.rfind(";"), clause.rfind(". "))
        if cut > 0:
            clause = clause[cut:]
        required = not BIOMARKER_NEGATION.search(clause)

        for alt in alts:
            payloads.append({"gene": gene, "alteration": alt,
                             "required": required})

    seen, unique = set(), []
    for p in payloads:
        key = (p["gene"], p["alteration"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(p)
    return unique


# =====================================================================
# PRIOR_THERAPY
# =====================================================================

# "prior" is the temporal preposition far more often than the adjective, so
# "prior to the first dose" must not read as a treatment-history claim.
PRIOR_CUE = re.compile(
    r"\bprior\b(?!\s+to)|\bpreviousl?y?\b|\breceived\b|\btreated\s+with\b|"
    r"\bexposure\s+to\b|\bfailed\b|\bprogress(?:ed|ion)\s+(?:on|after)\b|"
    r"\bpost[\s-]progression\s+on\b|"
    r"\brefractory\s+to\b|\bnaive\b|\buntreated\b|\bpre[\s-]?treated\b|"
    r"\bhas\s+had\b|\blines?\s+of\b|\bregimens?\b|\bpretreatment\b|"
    r"\bhistory\s+of\b|\bunderwent\b|\bundergone\b|\bdiscontinued\b",
    re.I,
)

# A criterion whose only claim is "prior therapy", with no class and no count.
BARE_PRIOR_THERAPY = re.compile(
    r"\bprior\s+(?:therap(?:y|ies)|treatments?|regimens?|SOC\s+therapy|"
    r"standard\s+of\s+care)\b|\bpreviously\s+received\b", re.I)

# Contexts where a named therapy is not a treatment-history claim.
PRIOR_CONTEXT_TRAP = re.compile(
    r"amenorrh\w*|menopaus\w*|childbearing|pregnan\w*|breast\s*feed\w*|"
    r"measurable\s+(?:or\s+non[\s-]measurable\s+)?disease|"
    r"measurable\s+lesion|tumou?r\s+samples?|archival|"
    r"amenable\b|eligibility\s+to\s+receive|planned\s+to\s+receive|"
    # therapy that EXISTS or is available, not therapy the patient had
    r"targeted\s+therapy\s+(?:for\s+[\w\s]{0,20})?exists|"
    r"therapy\s+is\s+accessible|approved\s+targeted\s+therapy|"
    # "radiation pneumonitis" is a condition, not a course of radiotherapy
    r"radiation[\s-](?:pneumonitis|induced|related\s+injury)|"
    r"radiation[\s-]induced\s+lung",
    re.I,
)

COUNT_NOUN = r"lines?|regimens?|courses?|cycles?|therapies|treatments?|" \
             r"prior\s+therap(?:y|ies)"

# "no more than 3 prior lines of therapy", "at least 1 line", "exactly one"
LINE_COUNT_RE = re.compile(
    rf"""(?P<op>no\s+more\s+than|not\s+more\s+than|at\s+least|no\s+less\s+than|
           up\s+to|maximum\s+of|minimum\s+of|exactly|only|a\s+maximum\s+of|
           [≥≤<>]=?)?\s*
        (?P<num>\d+|one|two|three|four|five)
        (?:\s*(?:-|to|–)\s*(?P<num2>\d+))?
        \s+(?:prior\s+|previous\s+|additional\s+)?(?:\w+\s+){{0,2}}?
        (?P<noun>{COUNT_NOUN})\b
    """,
    re.I | re.X,
)
COUNT_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}

MAX_OPS = {"no more than", "not more than", "up to", "maximum of",
           "a maximum of", "<=", "<"}
MIN_OPS = {"at least", "no less than", "minimum of", ">=", ">"}
EXACT_OPS = {"exactly", "only"}

# "Treatment-naive" / "previously untreated" is a prior-therapy claim in its own
# right, even when the sentence names no drug class. Bare "untreated" is not --
# it attaches to lesions far more often ("active, untreated brain metastases").
NAIVE_PAT = (r"(?:treatment|therapy|chemotherapy|systemic|therapies)[\s-]*"
             r"na[iï]ve|na[iï]ve\s+to\s+(?:treatment|therapy)|"
             r"previously\s+untreated|treatment[\s-]na[iï]ve")
NAIVE_RE = re.compile(NAIVE_PAT, re.I)

# The criterion asserts the therapy was NOT given. The lookahead is essential:
# "NO MORE THAN 3 prior lines" caps the count, it does not deny prior therapy,
# and reading it as a negation inverts the criterion.
PRIOR_NEGATION = re.compile(
    r"\b(?:no(?!\s+(?:more|less|fewer|greater)\s+than)|not|without|never)"
    r"\s+(?:\w+\s+){0,3}?"
    r"(?:prior|previous|received|receiving|treated|therapy|treatment|"
    r"exposure|lines?)\b"
    rf"|{NAIVE_PAT}",
    re.I,
)

SETTINGS = [
    ("neoadjuvant", r"neo[\s-]?adjuvant"),
    ("adjuvant", r"\badjuvant\b"),
    ("perioperative", r"perioperative"),
    ("first_line", r"first[\s-]line|\b1L\b|\bfirst\s+line\b"),
    ("advanced", r"advanced|metastatic|recurrent"),
]

PROGRESSED_RE = re.compile(
    r"progressed?\s+(?:on|after|during)|\bfailed\b|refractory\s+to|"
    r"intoleran\w+\s+(?:of|to)|relapsed?\s+(?:on|after)", re.I)


def _parse_line_counts(t):
    """(min_lines, max_lines, exact_lines, count_unit) or None."""
    for m in LINE_COUNT_RE.finditer(t):
        noun = m.group("noun").lower()
        unit = "cycles" if noun.startswith("cycle") else "lines"
        raw = m.group("num").lower()
        n = COUNT_WORDS.get(raw, None)
        if n is None:
            n = int(raw)
        if n > 20:
            continue
        n2 = int(m.group("num2")) if m.group("num2") else None
        op = (m.group("op") or "").lower().strip()

        if n2 is not None:
            return n, n2, None, unit
        if op in MAX_OPS:
            return None, n, None, unit
        if op in MIN_OPS:
            return n, None, None, unit
        if op in EXACT_OPS:
            return None, None, n, unit
        return None, None, n, unit
    return None


def compile_prior_therapies(text, polarity_flipped=False, context=(),
                            timed_classes=frozenset()):
    """Extract PRIOR_THERAPY payloads from one criterion.

    `polarity_flipped` says the splitter already turned "Participants must not
    have received X" into an exclusion. Reading that negation again here would
    double-negate: the predicate must assert the positive fact ("has had X") so
    that an exclusion being MET blocks the patient.

    `timed_classes` are classes this criterion already produced a WASHOUT for.
    "Prior radiotherapy within 2 weeks of the start of study drug" restricts
    WHEN the therapy was given, not WHETHER -- it is a washout, and emitting a
    standalone treatment-history predicate for it double-counts the criterion.
    A line count or a treatment-naive claim overrides this, since those are
    history requirements regardless of any window.
    """
    t = _normalize(text)
    # A parent header often supplies the cue: "Patients who have received the
    # following treatments must be excluded:" / "Any systemic anti-tumor
    # treatment, including radiotherapy".
    cue_text = t + " " + _normalize(" ".join(context))
    if (not PRIOR_CUE.search(cue_text) or PRIOR_CONTEXT_TRAP.search(t)
            or NOT_PRIOR_THERAPY_HARD.search(t)):
        return []

    classes = [(s, e, n) for s, e, n in find_classes(t)
               if n in ANTICANCER_CLASSES]
    counts = _parse_line_counts(t)
    naive = bool(NAIVE_RE.search(t))

    # The toxicity/recovery guard applies only when no specific therapy is
    # named. "Grade 3 toxicity to a prior checkpoint inhibitor" is a
    # prior-therapy exclusion; "unresolved toxicities from prior therapy" is a
    # recovery requirement.
    specific = [c for c in classes if c[2] != "ANTICANCER_THERAPY"]
    if NOT_PRIOR_THERAPY_SOFT.search(t) and not specific:
        return []

    if not classes and not counts and not naive:
        if not BARE_PRIOR_THERAPY.search(t):
            return []

    neg_text = t
    if polarity_flipped:
        neg_text = NEGATED_INCLUSION.sub(" ", neg_text)
    required = not PRIOR_NEGATION.search(neg_text)

    setting = next((name for name, pat in SETTINGS
                    if re.search(pat, t, re.I)), None)
    progressed = bool(PROGRESSED_RE.search(t))

    min_l, max_l, exact_l, unit = counts if counts else (None, None, None, None)

    if not classes:
        # "no more than 3 prior lines of therapy" names no class.
        return [{"drug_class": "ANY", "min_lines": min_l, "max_lines": max_l,
                 "exact_lines": exact_l, "count_unit": unit,
                 "required": required, "setting": setting,
                 "progressed_on": progressed}]

    out, seen = [], set()
    has_history_claim = bool(counts or naive)
    for _, _, name in classes:
        if name in seen:
            continue
        # Timed mention with nothing else asserted -> it is a washout only.
        if name in timed_classes and not has_history_claim:
            continue
        seen.add(name)
        out.append({"drug_class": name, "min_lines": min_l, "max_lines": max_l,
                    "exact_lines": exact_l, "count_unit": unit,
                    "required": required, "setting": setting,
                    "progressed_on": progressed})
    return out


# =====================================================================
# COMORBIDITY
# =====================================================================

# Registry prose glosses almost every term inline: "central nervous system
# (CNS) metastases", "interstitial lung disease (ILD)". The parenthetical
# splits the phrase the pattern is looking for. Blanking it with spaces of the
# same length keeps every character offset valid for qualifier lookup.
ABBREV_PAREN = re.compile(r"\([A-Z][A-Z0-9/\-]{1,9}\)")


def _blank_abbrev_parens(t):
    return ABBREV_PAREN.sub(lambda m: " " * len(m.group(0)), t)


def _qualifier_for(t, start, end):
    """Qualifier governing the condition at [start, end).

    Looked for in the condition's own clause. "Active infection ... ; stable
    brain metastases are eligible" must not lend "active" to the second.
    """
    lo = max(0, start - 70)
    window = t[lo:start]
    cut = max(window.rfind(";"), window.rfind(". "), window.rfind(") "))
    if cut >= 0:
        window = window[cut:]
    # The matched span is part of the window: several condition patterns
    # absorb their own qualifier ("severe hepatic disease", "unstable angina"),
    # and a preceding-text-only window would never see it.
    window += " " + t[start:end] + " " + t[end:end + 30]
    for name, pat in QUALIFIERS:
        if re.search(pat, window, re.I):
            return name
    return None


def compile_comorbidities(text, is_inclusion=False, polarity_flipped=False):
    """Extract COMORBIDITY payloads from one criterion.

    `excluded` follows the spec's field: True when having the condition
    disqualifies the patient. It is derived from the section polarity and any
    negation in the sentence, so the predicate reads the same way regardless of
    which section the trial happened to file it under.
    """
    t = _normalize(text)
    if CONDITION_TRAP.search(t):
        return []

    hits = scan(CONDITION_PATTERNS, _blank_abbrev_parens(t))
    if not hits:
        return []

    # "Participants must not have X" was already turned into an exclusion by
    # the splitter; reading that negation again would cancel it out.
    neg_text = t
    if polarity_flipped:
        neg_text = NEGATED_INCLUSION.sub(" ", neg_text)

    permitted = bool(PERMITTED.search(t))

    out, seen = [], set()
    for s, e, cond in hits:
        if cond in seen:
            continue
        seen.add(cond)

        clause_start = max(0, s - 40)
        negated = bool(CONDITION_NEGATION.search(neg_text[clause_start:s]))
        if permitted:
            excluded = False
        elif is_inclusion:
            excluded = negated
        else:
            excluded = not negated

        out.append({
            "condition": cond,
            "qualifier": _qualifier_for(t, s, e),
            "excluded": excluded,
        })
    return out


def compile_criterion(raw):
    """RawCriterion -> list[Criterion]. Uncompiled text falls through to FREE_TEXT."""
    out = []

    def emit(ptype, mut, payload):
        out.append(Criterion(
            trial_id=raw.trial_id,
            raw_text=raw.raw_text,
            is_inclusion=raw.is_inclusion,
            predicate_type=ptype,
            mutability=mut,
            payload=payload,
            compiled=True,
            start=raw.start,
            end=raw.end,
        ))

    for p in compile_lab_thresholds(raw.raw_text):
        emit("LAB_THRESHOLD", Mutability.CORRECTABLE, p)

    washouts = compile_washouts(raw.raw_text, getattr(raw, "context", ()))
    for p in washouts:
        emit("WASHOUT", Mutability.TEMPORAL, p)
    timed = {p["drug_or_class"] for p in washouts}

    for p in compile_age(raw.raw_text):
        emit("AGE", Mutability.IMMUTABLE, p)

    for p in compile_performance_status(raw.raw_text):
        emit("PERFORMANCE_STATUS", Mutability.CORRECTABLE, p)

    for p in compile_histology(raw.raw_text):
        emit("HISTOLOGY", Mutability.IMMUTABLE, p)

    for p in compile_stage(raw.raw_text):
        emit("STAGE", Mutability.IMMUTABLE, p)

    for p in compile_biomarkers(raw.raw_text):
        emit("BIOMARKER", Mutability.IMMUTABLE, p)

    for p in compile_prior_therapies(
            raw.raw_text, getattr(raw, "polarity_flipped", False),
            getattr(raw, "context", ()), timed):
        emit("PRIOR_THERAPY", Mutability.IMMUTABLE, p)

    for p in compile_comorbidities(
            raw.raw_text, raw.is_inclusion,
            getattr(raw, "polarity_flipped", False)):
        emit("COMORBIDITY", Mutability.UNKNOWN, p)

    if not out:
        out.append(Criterion(
            trial_id=raw.trial_id,
            raw_text=raw.raw_text,
            is_inclusion=raw.is_inclusion,
            predicate_type="FREE_TEXT",
            mutability=Mutability.UNKNOWN,
            payload={},
            compiled=False,
            start=raw.start,
            end=raw.end,
        ))
    return out
