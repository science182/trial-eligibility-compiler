"""Patient record with span-level provenance.

Every field that came from free text carries `span`: character offsets into the
source report. The UI highlights the originating sentence when a criterion row
is clicked, and a field with no span is one the system inferred rather than
read -- which the evaluator surfaces rather than hides.
"""

from dataclasses import dataclass, field
from datetime import date
from typing import Optional


@dataclass
class Sourced:
    """A value plus where in the report it came from."""
    value: object
    span: Optional[tuple] = None      # (start, end) char offsets
    text: Optional[str] = None        # verbatim source snippet

    def __repr__(self):
        return f"Sourced({self.value!r}@{self.span})"


@dataclass
class LabValue:
    analyte: str
    value: float                      # already in canonical units
    unit: str
    date: Optional[date] = None
    uln: Optional[float] = None       # institutional limit, if the report gives one
    lln: Optional[float] = None
    span: Optional[tuple] = None
    text: Optional[str] = None


@dataclass
class Biomarker:
    gene: str
    alteration: str                   # normalized code, or "UNKNOWN"
    vaf: Optional[float] = None
    span: Optional[tuple] = None
    text: Optional[str] = None


@dataclass
class PriorTherapy:
    drug: Optional[str] = None
    drug_class: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    best_response: Optional[str] = None
    setting: Optional[str] = None
    line: Optional[int] = None
    progressed: Optional[bool] = None
    span: Optional[tuple] = None
    text: Optional[str] = None


@dataclass
class PatientRecord:
    index_date: date                              # "today" for this query
    report_text: str = ""

    age: Optional[Sourced] = None
    sex: Optional[Sourced] = None
    histology: Optional[Sourced] = None            # normalized code
    stage: Optional[Sourced] = None
    ecog: Optional[Sourced] = None
    karnofsky: Optional[Sourced] = None

    biomarkers: list = field(default_factory=list)          # [Biomarker]
    labs: dict = field(default_factory=dict)                # analyte -> LabValue
    prior_therapies: list = field(default_factory=list)     # [PriorTherapy]
    comorbidities: list = field(default_factory=list)       # [Sourced(condition)]
    last_dose_dates: dict = field(default_factory=dict)     # class -> date
    event_dates: dict = field(default_factory=dict)         # event -> date

    # Conditions and therapy classes the patient is explicitly documented NOT
    # to have. Absence from `comorbidities` / `prior_therapies` means "not
    # recorded", not "absent" -- the difference between UNDETERMINED and
    # NOT_MET.
    negative_findings: set = field(default_factory=set)

    # Where each documented absence was stated, keyed the way the evaluator
    # names it ("comorbidity:HIV", "therapy:RADIOTHERAPY"). A documented
    # negative is evidence like any other -- "no brain metastases" is the
    # sentence a NOT_MET verdict rests on -- so it has to be highlightable.
    # Kept beside negative_findings rather than inside it because membership
    # tests on that set are on the evaluation path and stay cheapest as a set.
    negative_spans: dict = field(default_factory=dict)

    # True when the treatment-history section is meant to be exhaustive, as in
    # an oncology progress note. Only then does a therapy class being absent
    # from the list mean the patient did not receive it; otherwise silence is
    # UNDETERMINED. Line counts are meaningless without this.
    therapy_history_complete: bool = False

    # Genes with a reported result. A gene that was never tested is
    # UNDETERMINED, never "negative".
    genes_tested: set = field(default_factory=set)

    def lab(self, analyte):
        return self.labs.get(analyte)

    def has_condition(self, condition):
        """True / False / None, where None means the record is silent."""
        for c in self.comorbidities:
            if c.value == condition:
                return True
        if condition in self.negative_findings:
            return False
        return None

    def biomarker(self, gene):
        return [b for b in self.biomarkers if b.gene == gene]

    def therapy_classes(self):
        return {t.drug_class for t in self.prior_therapies if t.drug_class}

    def date_for(self, key):
        """Anchor date for a washout subject: therapy class or clinical event."""
        return self.last_dose_dates.get(key) or self.event_dates.get(key)

    def spans(self):
        """Every (field_name, span) pair, for UI highlighting."""
        out = []
        for name in ("age", "sex", "histology", "stage", "ecog", "karnofsky"):
            v = getattr(self, name)
            if v is not None and v.span:
                out.append((name, v.span))
        for a, lv in self.labs.items():
            if lv.span:
                out.append((f"lab:{a}", lv.span))
        for b in self.biomarkers:
            if b.span:
                out.append((f"biomarker:{b.gene}", b.span))
        for t in self.prior_therapies:
            if t.span:
                out.append((f"therapy:{t.drug_class or t.drug}", t.span))
        for c in self.comorbidities:
            if c.span:
                out.append((f"comorbidity:{c.value}", c.span))
        # Documented absences last, and only where nothing positive claimed the
        # key: a stated positive always outranks a negation of the same code
        # elsewhere in the note.
        claimed = {k for k, _ in out}
        for key, span in self.negative_spans.items():
            if key not in claimed and span:
                out.append((key, span))
        return out
