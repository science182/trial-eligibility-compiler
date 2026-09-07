"""Predicate evaluation. Pure Python -- no model calls, ever.

Every numeric comparison, unit-resolved threshold, and date computation in the
system happens here. The compiler decides what a sentence asserts; this decides
whether a patient satisfies it.

VERDICT SEMANTICS (a deliberate simplification of the build spec)

The spec defines MET as "the predicate is true", so the aggregation rule reads
"all inclusion criteria MET, no exclusion criteria MET". This module instead
defines:

    MET  =  the patient SATISFIES this criterion.

Polarity -- inclusion vs exclusion, `required`, `excluded`, and textual
negation -- is resolved here, where the payload semantics are known, rather
than in the aggregator. The aggregation rule becomes "every criterion MET".

The two formulations are equivalent, but this one has a single place where
polarity is applied. Polarity has already produced three separate bugs in this
project (prose-negated inclusions, double-negated prior therapy, double-negated
comorbidity), all from applying it twice in different layers. `is_inclusion` is
still preserved on every Criterion, so the UI can group rows normally.
"""

import re
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Optional

from dates import add_window
from display import human_date, sentence, term
from drugs import ANTICANCER_CLASSES
from units import reference_limit


class Verdict(Enum):
    MET = "met"
    NOT_MET = "not_met"
    UNDETERMINED = "undetermined"   # the record lacks the field
    PENDING = "pending"             # will be met on a computable date


@dataclass
class Result:
    verdict: Verdict
    criterion: object                       # the Criterion that was evaluated
    reason: str = ""                        # one line, shown in the UI
    eligible_date: Optional[date] = None    # set when PENDING
    anchor_date: Optional[date] = None      # what the date was computed from
    missing: tuple = ()                     # field names needed to resolve
    used: tuple = ()                        # patient fields this verdict read,
                                            # so the UI can highlight the source
    assumed: tuple = ()                     # defaults used, e.g. a fallback ULN
    # A conditional variant whose condition does not hold for this patient
    # ("<= 5 x ULN if liver metastases" for a patient without them). It is not
    # satisfied, it simply does not govern -- so group combination drops it
    # rather than counting it as a passing alternative.
    applicable: bool = True

    @property
    def blocking(self):
        return self.verdict in (Verdict.NOT_MET, Verdict.PENDING)


def _u(criterion, missing, reason):
    return Result(Verdict.UNDETERMINED, criterion, reason, missing=tuple(missing))


FLIP = {Verdict.MET: Verdict.NOT_MET, Verdict.NOT_MET: Verdict.MET}


def _satisfy(verdict, criterion):
    """Predicate truth -> whether the PATIENT SATISFIES the criterion.

    An exclusion criterion is satisfied when its predicate is FALSE: "QTcF >
    470 msec" in an exclusion section means a patient at 471 fails, and one at
    460 passes. Evaluators that compute raw predicate truth must run their
    verdict through this.

    HISTOLOGY and COMORBIDITY are deliberately NOT routed here: their payloads
    (`excluded_codes`, `excluded`) already encode section polarity, so flipping
    again would double-negate.
    """
    if criterion.is_inclusion:
        return verdict
    return FLIP.get(verdict, verdict)


# ---------------------------------------------------------------- LAB

OPS = {
    ">=": lambda a, b: a >= b,
    ">": lambda a, b: a > b,
    "<=": lambda a, b: a <= b,
    "<": lambda a, b: a < b,
    "=": lambda a, b: a == b,
}

CONDITION_FIELDS = {
    "liver_metastases": "LIVER_METASTASES",
    "no_liver_metastases": "LIVER_METASTASES",
    "gilberts": "GILBERTS_SYNDROME",
}


def _condition_applies(cond, patient):
    """Does this threshold's condition hold for the patient? None = unknown."""
    if cond is None:
        return True
    key = CONDITION_FIELDS.get(cond)
    if key is None:
        return None
    has = patient.has_condition(key)
    if has is None:
        return None
    return (not has) if cond == "no_liver_metastases" else has


def _resolve_threshold(p, lab, patient):
    """Threshold in canonical units. Returns (value, assumed_default: bool)."""
    if p["basis"] == "absolute":
        return p["value"], False
    kind = p["basis"]                      # "uln" or "lln"
    limit = (lab.uln if kind == "uln" else lab.lln) if lab else None
    # Round the product: 1.5 * 1.2 is 1.7999999999999998 in binary floating
    # point, so a patient at exactly 1.8 would fail a "<= 1.5 x ULN" bound.
    # Silent, and precisely on the boundary the protocol cares about.
    if limit is not None:
        return round(p["value"] * limit, 10), False
    fallback = reference_limit(p["analyte"], kind)
    if fallback is None:
        return None, False
    return round(p["value"] * fallback, 10), True


def eval_lab(c, patient):
    p = c.payload
    src = (f"lab:{p['analyte']}",)
    lab = patient.lab(p["analyte"])
    if lab is None:
        return _u(c, [f"lab:{p['analyte']}"],
                  f"{sentence(p['analyte'])} not reported")

    applies = _condition_applies(p.get("condition"), patient)
    if applies is None:
        return _u(c, [f"condition:{p['condition']}"],
                  f"cannot tell whether {p['condition']} applies")
    if applies is False:
        return Result(Verdict.MET, c,
                      f"variant for {p['condition']} does not govern",
                      applicable=False)

    threshold, assumed = _resolve_threshold(p, lab, patient)
    if threshold is None:
        return _u(c, [f"reference_limit:{p['analyte']}"],
                  f"no reference limit available for {term(p['analyte'])}")

    ok = OPS[p["operator"]](lab.value, threshold)
    shown = f"{lab.value:g} {lab.unit}"
    req = (f"{p['operator']} {threshold:g} {lab.unit}"
           if p["basis"] == "absolute"
           else f"{p['operator']} {p['value']:g}x{p['basis'].upper()}"
                f" (= {threshold:g} {lab.unit})")
    return Result(
        _satisfy(Verdict.MET if ok else Verdict.NOT_MET, c), c,
        f"{sentence(p['analyte'])} {shown}, requires {req}",
        used=src,
        assumed=("default reference limit",) if assumed else (),
    )


# ------------------------------------------------------------ WASHOUT

def eval_washout(c, patient):
    p = c.payload
    key = p["drug_or_class"]
    label = term(key)
    anchor = patient.date_for(key)
    if anchor is None:
        # A washout for something the patient never had is already satisfied --
        # there is nothing to wait for. This only holds where the record can
        # actually support the claim.
        never_had = key in patient.negative_findings or (
            p.get("subject_kind") == "therapy"
            and patient.therapy_history_complete
            and key not in patient.therapy_classes()
        )
        if never_had:
            return Result(Verdict.MET, c, f"no prior {label}; nothing to wash out",
                          used=(f"therapy:{key}",))
        # Otherwise never guess an anchor: no date means no eligibility date.
        return _u(c, [f"date:{key}"], f"no recorded date for {label}")

    window_end = add_window(anchor, p["amount"], p["unit"])
    if patient.index_date >= window_end:
        return Result(Verdict.MET, c,
                      f"{p['amount']:g} {p['unit']} elapsed since "
                      f"{human_date(anchor)}",
                      anchor_date=anchor, used=(f"therapy:{key}",))

    note = ""
    if p.get("half_lives") and p.get("whichever") == "longer":
        note = (f"; protocol also allows {p['half_lives']} half-lives, "
                "whichever is longer")
    return Result(
        Verdict.PENDING, c,
        f"{p['amount']:g} {p['unit']} washout from {human_date(anchor)}{note}",
        eligible_date=window_end, anchor_date=anchor,
        used=(f"therapy:{key}",),
    )


# ---------------------------------------------------------------- AGE

def eval_age(c, patient):
    p = c.payload
    if patient.age is None:
        return _u(c, ["age"], "Age not reported")
    a = patient.age.value
    lo, hi = p.get("min_years"), p.get("max_years")
    if lo is not None and a < lo:
        return Result(_satisfy(Verdict.NOT_MET, c), c,
                      f"Age {a}, requires >= {lo}", used=("age",))
    if hi is not None and a > hi:
        return Result(_satisfy(Verdict.NOT_MET, c), c,
                      f"Age {a}, requires <= {hi}", used=("age",))
    # "age 64 within 18" is not a sentence. Say what the bound actually is.
    if lo is not None and hi is not None:
        bounds = f"the {lo}\u2013{hi} range"
    elif lo is not None:
        bounds = f"the minimum of {lo}"
    elif hi is not None:
        bounds = f"the maximum of {hi}"
    else:
        bounds = "the stated range"
    return Result(_satisfy(Verdict.MET, c), c,
                  f"Age {a} meets {bounds}" if c.is_inclusion
                  else f"Age {a} falls in the excluded range", used=("age",))


# ------------------------------------------- PERFORMANCE_STATUS

def eval_performance_status(c, patient):
    p = c.payload
    scale = p["scale"]
    src = patient.karnofsky if scale == "KARNOFSKY" else patient.ecog
    if src is None:
        return _u(c, [scale.lower()], f"{sentence(scale)} not reported")
    v = src.value
    f = ("karnofsky",) if scale == "KARNOFSKY" else ("ecog",)

    if p.get("operator") and p.get("value") is not None:
        ok = OPS[p["operator"]](v, p["value"])
        return Result(_satisfy(Verdict.MET if ok else Verdict.NOT_MET, c), c,
                      f"{sentence(scale)} {v}, requires "
                      f"{p['operator']} {p['value']}",
                      used=f)

    lo, hi = p.get("min_value"), p.get("max_value")
    band = f"{lo}-{hi}"
    if lo is not None and v < lo:
        return Result(_satisfy(Verdict.NOT_MET, c), c,
                      f"{sentence(scale)} {v}, requires >= {lo}" if c.is_inclusion
                      else f"{sentence(scale)} {v} is below the excluded {band}",
                      used=f)
    if hi is not None and v > hi:
        return Result(_satisfy(Verdict.NOT_MET, c), c,
                      f"{sentence(scale)} {v}, requires <= {hi}" if c.is_inclusion
                      else f"{sentence(scale)} {v} is above the excluded {band}",
                      used=f)
    return Result(_satisfy(Verdict.MET, c), c,
                  f"{sentence(scale)} {v} within {band}" if c.is_inclusion
                  else f"{sentence(scale)} {v} is within the excluded {band}",
                  used=f)


# --------------------------------------------------------- HISTOLOGY

# A subtype satisfies a requirement for its parent type.
HISTOLOGY_PARENTS = {
    "NSCLC_SQUAMOUS": {"NSCLC"},
    "NSCLC_NONSQUAMOUS": {"NSCLC"},
    "ADENOCARCINOMA": {"NSCLC_NONSQUAMOUS", "NSCLC"},
    "LARGE_CELL": {"NSCLC"},
    "SARCOMATOID": {"NSCLC"},
    "NSCLC": {"SOLID_TUMOR"},
    "SCLC": {"SOLID_TUMOR"},
    "LCNEC": {"SOLID_TUMOR"},
}


def _histology_matches(patient_code, target):
    if patient_code == target:
        return True
    seen, stack = set(), [patient_code]
    while stack:
        cur = stack.pop()
        if cur == target:
            return True
        for parent in HISTOLOGY_PARENTS.get(cur, ()):
            if parent not in seen:
                seen.add(parent)
                stack.append(parent)
    return False


def eval_histology(c, patient):
    p = c.payload
    if patient.histology is None:
        return _u(c, ["histology"], "histology not reported")
    h = patient.histology.value

    for bad in p.get("excluded_codes", []):
        if _histology_matches(h, bad):
            return Result(Verdict.NOT_MET, c, f"{sentence(h)} is excluded",
                          used=("histology",))
    allowed = p.get("allowed_codes", [])
    if not allowed:
        return Result(Verdict.MET, c, f"{sentence(h)} not excluded",
                      used=("histology",))
    if any(_histology_matches(h, a) for a in allowed):
        return Result(Verdict.MET, c,
                      f"{sentence(h)} matches "
                      f"{', '.join(term(a) for a in allowed)}",
                      used=("histology",))
    return Result(Verdict.NOT_MET, c,
                  f"{sentence(h)}, requires "
                  f"{' or '.join(term(a) for a in allowed)}",
                  used=("histology",))



def _named(c, subject):
    """Reason text when the patient's value is one the criterion names.

    On an inclusion criterion that fact makes the patient eligible; on an
    exclusion criterion the identical fact is what rules them out. `_satisfy`
    already flips the verdict -- the reason has to flip too, or a blocked
    trial explains itself with the word "eligible". That is not a cosmetic
    problem: the interface groups ruled-out trials by this string.
    """
    return f"{subject} is eligible" if c.is_inclusion else f"{subject} is excluded"


# ------------------------------------------------------------- STAGE

def eval_stage(c, patient):
    p = c.payload
    if patient.stage is None:
        return _u(c, ["stage"], "stage not reported")
    s = patient.stage.value.upper()
    allowed = p["allowed_stages"]
    if s in allowed:
        return Result(_satisfy(Verdict.MET, c), c,
                      _named(c, f"Stage {s}"), used=("stage",))
    # A bare stage in the record satisfies a requirement for any of its
    # substages only if the requirement names the bare stage too.
    detail = ", ".join(allowed)
    return Result(_satisfy(Verdict.NOT_MET, c), c,
                  f"Stage {s}, requires {detail}" if c.is_inclusion
                  else f"Stage {s} is not among the excluded ({detail})",
                  used=("stage",))



# Variant codes are read as codes -- "L858R", not "l858r" -- while word-like
# alteration names read better lower case. The reason string is now the headline
# for a whole group of ruled-out trials, so this is legibility, not polish.
_VARIANT = re.compile(r"^[A-Z]\d{2,4}[A-Z]?$")
_EXON = re.compile(r"^EXON(\d+)(DEL|INS|SKIP)$")


def _alt_label(alt):
    if _VARIANT.match(alt):
        return alt
    m = _EXON.match(alt)
    if m:
        return f"exon {m.group(1)} {m.group(2).lower()}"
    return alt.lower().replace("_", " ")


# --------------------------------------------------------- BIOMARKER

GENERIC_ALTS = {"MUTATION", "POSITIVE", "FUSION", "AMPLIFICATION",
                "OVEREXPRESSION"}


def eval_biomarker(c, patient):
    p = c.payload
    gene, alt, required = p["gene"], p["alteration"], p["required"]
    found = patient.biomarker(gene)

    if not found:
        if gene in patient.genes_tested:
            present = False
        else:
            return _u(c, [f"biomarker:{gene}"], f"{term(gene)} status not reported")
    else:
        present = any(
            alt in GENERIC_ALTS or b.alteration == alt or
            b.alteration == "UNKNOWN"
            for b in found
        )

    label = f"{term(gene)} {_alt_label(alt)}"
    src = (f"biomarker:{gene}",)
    asserted = present if required else not present
    return Result(_satisfy(Verdict.MET if asserted else Verdict.NOT_MET, c), c,
                  f"{label} {'present' if present else 'absent'}"
                  f"{', required' if required else ', must be absent'}",
                  used=src)


# ----------------------------------------------------- PRIOR_THERAPY

def eval_prior_therapy(c, patient):
    p = c.payload
    cls, required = p["drug_class"], p["required"]
    src = (f"therapy:{cls}",)

    if (not patient.prior_therapies and not patient.therapy_history_complete
            and cls not in patient.negative_findings):
        return _u(c, ["prior_therapies"], "treatment history not reported")

    # A criterion naming the parent class is satisfied by any child of it:
    # "previous TKI" covers a patient whose record says EGFR_TKI.
    subsumes = {"TKI": {"EGFR_TKI", "ALK_TKI", "TKI"},
                "IMMUNOTHERAPY": {"CHECKPOINT_INHIBITOR", "IMMUNOTHERAPY"},
                "ANTICANCER_THERAPY": ANTICANCER_CLASSES}
    wanted = subsumes.get(cls, {cls})
    if cls == "ANY":
        matches = list(patient.prior_therapies)
    else:
        matches = [t for t in patient.prior_therapies if t.drug_class in wanted]

    # A record listing two systemic therapies does not assert the patient never
    # had surgery. Absence only means absence when the history is exhaustive or
    # the class is explicitly ruled out.
    if not matches and cls != "ANY":
        if not (patient.therapy_history_complete
                or cls in patient.negative_findings):
            return _u(c, [f"therapy:{cls}"],
                      f"no record of prior {cls.lower().replace('_', ' ')}")

    # Line counts are only meaningful against a countable history.
    n = len({t.line for t in matches if t.line is not None}) or len(matches)
    lo, hi, exact = p.get("min_lines"), p.get("max_lines"), p.get("exact_lines")
    if any(x is not None for x in (lo, hi, exact)):
        if p.get("count_unit") == "cycles":
            return _u(c, ["prior_therapies:cycles"],
                      "cycle counts are not recorded on the patient record")
        if not patient.therapy_history_complete:
            return _u(c, ["prior_therapies"],
                      "treatment history is not marked complete; "
                      "lines cannot be counted")
        if exact is not None and n != exact:
            return Result(_satisfy(Verdict.NOT_MET, c), c,
                          f"{n} prior line(s), requires exactly {exact}", used=src)
        if lo is not None and n < lo:
            return Result(_satisfy(Verdict.NOT_MET, c), c,
                          f"{n} prior line(s), requires >= {lo}", used=src)
        if hi is not None and n > hi:
            return Result(_satisfy(Verdict.NOT_MET, c), c,
                          f"{n} prior line(s), requires <= {hi}", used=src)
        return Result(_satisfy(Verdict.MET, c), c,
                      f"{n} prior line(s) within limit" if c.is_inclusion
                      else f"{n} prior line(s) falls in the excluded range",
                      used=src)

    present = bool(matches)
    if p.get("progressed_on") and present:
        prog = [t for t in matches if t.progressed]
        if not prog and all(t.progressed is None for t in matches):
            return _u(c, [f"progression:{cls}"],
                      f"progression status on {term(cls)} not recorded")
        present = bool(prog)

    name = ("systemic therapy of any kind" if cls == "ANY"
            else cls.lower().replace("_", " "))
    # Reaching here means absence is KNOWN -- an unknown history returned
    # UNDETERMINED above. "not recorded" would misdescribe a real finding.
    asserted = present if required else not present
    return Result(_satisfy(Verdict.MET if asserted else Verdict.NOT_MET, c), c,
                  f"prior {name} {'on record' if present else 'never given'}",
                  used=src)


# ------------------------------------------------------- COMORBIDITY

def eval_comorbidity(c, patient):
    p = c.payload
    cond = p["condition"]
    has = patient.has_condition(cond)
    label = cond.lower().replace("_", " ")

    if has is None:
        return _u(c, [f"comorbidity:{cond}"], f"{label} status not reported")

    src = (f"comorbidity:{cond}",)
    if not p["excluded"]:
        return Result(Verdict.MET, c, f"{label} permitted", used=src)
    if not has:
        return Result(Verdict.MET, c, f"no {label}", used=src)

    # Present and disqualifying. A qualifier the record contradicts is still a
    # block -- the evaluator does not second-guess the criterion.
    return Result(Verdict.NOT_MET, c, f"{label} present and excluded",
                  used=src)


# --------------------------------------------------------- dispatch

EVALUATORS = {
    "LAB_THRESHOLD": eval_lab,
    "WASHOUT": eval_washout,
    "AGE": eval_age,
    "PERFORMANCE_STATUS": eval_performance_status,
    "HISTOLOGY": eval_histology,
    "STAGE": eval_stage,
    "BIOMARKER": eval_biomarker,
    "PRIOR_THERAPY": eval_prior_therapy,
    "COMORBIDITY": eval_comorbidity,
}


def evaluate_predicate(c, patient):
    """One compiled Criterion against a patient. Never raises on bad data."""
    fn = EVALUATORS.get(c.predicate_type)
    if fn is None:
        return _u(c, [], "free text, not evaluated")
    try:
        return fn(c, patient)
    except Exception as e:                       # noqa: BLE001
        # A malformed payload must abstain, never assert a verdict.
        return _u(c, [], f"evaluation error: {type(e).__name__}: {e}")


ORDER = {Verdict.NOT_MET: 0, Verdict.PENDING: 1,
         Verdict.UNDETERMINED: 2, Verdict.MET: 3}


def _live(results):
    """Drop variants whose condition does not govern this patient."""
    live = [r for r in results if r.applicable]
    return live or results


def _combine_or(results):
    """Best outcome wins: one satisfiable route through a disjunction is enough."""
    return max(_live(results), key=lambda r: ORDER[r.verdict])


def _combine_and(results):
    """Worst outcome wins."""
    return min(_live(results), key=lambda r: ORDER[r.verdict])


def evaluate_criterion(criteria, patient):
    """Evaluate all predicates compiled from ONE source criterion.

    Predicates sharing a `group` are alternatives (OR) -- "creatinine <= 1.5 x
    ULN OR CrCl >= 40 mL/min" is one requirement with two routes, and passing
    either satisfies it. Separate groups are joint requirements (AND).
    """
    if not criteria:
        return None
    results = [evaluate_predicate(c, patient) for c in criteria]

    groups = {}
    for r in results:
        g = r.criterion.payload.get("group", id(r.criterion))
        groups.setdefault(g, []).append(r)

    per_group = [_combine_or(rs) if len(rs) > 1 else rs[0]
                 for rs in groups.values()]
    return _combine_and(per_group)
