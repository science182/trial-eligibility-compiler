r"""Eligibility block -> individual criteria.

Registry text is messy in ways that break naive line splitting:

  * numbering appears as `1.`, `1)`, `7\.`, `8.no-space`, `-`, `*`, or nothing
  * a criterion's content can sit on a later line, after a BLANK line, indented
    under its marker -- splitting on blank lines orphans the predicate from its
    subject ("ALT and AST" / "" / "<= 3.0 x ULN if no liver involvement")
  * list hierarchy is carried by indentation, and a parent header often holds
    the time window that governs its children ("Any of the following within 6
    months before the first dose:")
  * section headers are decorated ("Phase 1b Exclusion Criteria:"), so an exact
    match on "Exclusion Criteria" silently files exclusions as inclusions
  * inclusion sections state exclusions in prose ("Participants must not have...")

Every emitted criterion keeps verbatim `raw_text` plus (start, end) character
offsets into the original block. Ancestor headers ride along in `context`
rather than being spliced into raw_text, so provenance stays exact.
"""

import re
from dataclasses import dataclass, field

# A list marker at the start of a line: "1.", "1)", "7\.", "(1)", "-", "*", "a."
MARKER = re.compile(r"^(\s*)((?:[\(\[]?\d{1,2}[\)\.\]\\]+|[a-z][\)\.]|[ivx]+\.|[\-\*•·o])\s*)")

# Trailing registry boilerplate that is not a criterion.
BOILERPLATE = re.compile(
    r"(not intended to contain all considerations|other protocol.defined "
    r"(inclusion|exclusion)|please note|refer to the protocol|"
    r"other inclusion/exclusion criteria may apply)",
    re.I,
)

MIN_LEN = 8

# ------------------------------------------------------------ section headers

HDR_CORE = re.compile(r"\b(inclusion|exclusion)\s+criteri(?:a|on)\b", re.I)
# Residue words that mean the line is a sentence about criteria, not a heading:
# "Other inclusion/exclusion criteria may apply."
HDR_REJECT = re.compile(
    r"\b(may|will|must|should|shall|are|is|were|was|apply|applies|meeting|"
    r"met|listed|below|above|described|defined|disqualified|entering)\b",
    re.I,
)


def header_kind(line):
    """'inclusion' | 'exclusion' | None for a section-heading line."""
    s = line.strip()
    if not s or len(s) > 70:
        return None
    m = HDR_CORE.search(s)
    if not m:
        return None
    residue = s[:m.start()] + s[m.end():]
    residue = re.sub(r"[^A-Za-z0-9 ]", " ", residue).strip()
    if HDR_REJECT.search(residue) or len(residue) > 30:
        return None
    return m.group(1).lower()


# ------------------------------------------------------------ list headers

COMPARISON = re.compile(r"[<>≥≤]|\b(at least|no more than|no less than|"
                        r"greater than|less than|not exceed)\b", re.I)


def is_list_header(text):
    """A line that introduces sub-items rather than asserting a criterion.

    Must not swallow real criteria that happen to end in a colon, so anything
    carrying a comparison ("...or CrCl >= 30 mL/min. ...equation should be
    used:") stays a criterion.
    """
    t = text.rstrip()
    return (
        t.endswith(":")
        and len(t) < 150
        and not COMPARISON.search(t)
    )


# --------------------------------------------------------- prose polarity

# An inclusion section that says "Participants must not have X" is stating an
# exclusion. Left unflipped, the evaluator would require X to be true.
NEGATED_INCLUSION = re.compile(
    r"\b(?:must|should|shall|will)\s+not\s+"
    r"(?:have|be|been|receive|be\s+receiving|undergo|report)\b"
    r"|\bare\s+not\s+eligible\b|\bis\s+not\s+eligible\b",
    re.I,
)


@dataclass
class RawCriterion:
    trial_id: str
    raw_text: str
    is_inclusion: bool
    start: int
    end: int
    context: tuple = ()          # ancestor headers, outermost first
    polarity_flipped: bool = False

    @property
    def text_with_context(self):
        """Criterion text prefixed by its ancestor headers, for the compiler.

        Used for predicate extraction only -- never shown as provenance.
        """
        return " ".join(list(self.context) + [self.raw_text])


@dataclass
class _Line:
    indent: int
    content_indent: int
    body: str
    marked: bool
    offset: int


def _scan_lines(text):
    out = []
    off = 0
    for line in text.split("\n"):
        stripped = line.strip()
        if not stripped:
            out.append(None)          # blank: paragraph break, not a flush
            off += len(line) + 1
            continue
        m = MARKER.match(line)
        if m:
            indent = len(m.group(1))
            body_off = off + m.end()
            out.append(_Line(indent, indent + len(m.group(2)), line[m.end():],
                             True, body_off))
        else:
            indent = len(line) - len(line.lstrip())
            out.append(_Line(indent, indent, stripped, False, off + indent))
        off += len(line) + 1
    return out


def split_block(text, trial_id=""):
    """Split one eligibility block into criteria."""
    if not text or not text.strip():
        return []

    lines = _scan_lines(text)
    out = []

    # Registry blocks with no header at all are overwhelmingly inclusion lists.
    is_incl = True
    stack = []                     # [(indent, header_text)] ancestor headers
    buf = None                     # dict(parts, indent, content_indent, start, incl)

    def flush():
        nonlocal buf
        if buf is None:
            return
        raw = re.sub(r"\s+", " ", " ".join(buf["parts"])).strip()
        buf_indent = buf["indent"]
        buf = None
        if len(raw) < MIN_LEN or BOILERPLATE.search(raw):
            return

        while stack and stack[-1][0] >= buf_indent:
            stack.pop()

        if is_list_header(raw):
            stack.append((buf_indent, raw))
            return                 # structure, not a checkable criterion

        incl = buf_incl[0]
        flipped = False
        if incl and NEGATED_INCLUSION.search(raw):
            incl, flipped = False, True

        out.append(RawCriterion(
            trial_id=trial_id,
            raw_text=raw,
            is_inclusion=incl,
            start=buf_start[0],
            end=buf_start[0] + len(raw),
            context=tuple(h for _, h in stack),
            polarity_flipped=flipped,
        ))

    buf_incl = [True]
    buf_start = [0]

    for ln in lines:
        if ln is None:
            continue               # blank lines never terminate a criterion

        kind = header_kind(ln.body)
        if kind:
            flush()
            is_incl = kind == "inclusion"
            stack.clear()
            continue

        if ln.marked:
            flush()
            buf = {"parts": [ln.body], "indent": ln.indent,
                   "content_indent": ln.content_indent}
            buf_incl[0], buf_start[0] = is_incl, ln.offset
            continue

        # Unmarked line: a continuation if it is indented into the open
        # criterion's content column, otherwise a new bare criterion.
        if buf is not None and ln.indent >= buf["content_indent"]:
            buf["parts"].append(ln.body)
            continue
        if buf is not None and ln.indent >= buf["indent"] and not stack:
            buf["parts"].append(ln.body)
            continue

        flush()
        buf = {"parts": [ln.body], "indent": ln.indent,
               "content_indent": ln.indent}
        buf_incl[0], buf_start[0] = is_incl, ln.offset

    flush()
    return out


# NOTE: an earlier version split bundled lines ("ANC >=1.5, PLT >=100, Hb >=90")
# into one criterion per clause. That is now handled in the compiler, which
# emits a predicate per analyte from a single criterion. Splitting on commas at
# the text level was also lossy: it tore "<= 3.0 x ULN if no liver involvement,
# or <= 5 x ULN with liver involvement" into two criteria and destroyed the
# conditional variant, and it truncated Gilbert's-syndrome carve-outs.


if __name__ == "__main__":
    import json
    from pathlib import Path

    ROOT = Path(__file__).resolve().parents[1]
    trials = [
        json.loads(l)
        for l in (ROOT / "data" / "raw" / "nsclc_trials.jsonl").read_text().splitlines()
    ]
    total = flipped = with_ctx = 0
    for t in trials:
        for c in split_block(t["eligibility_text"], t["nct_id"]):
            total += 1
            flipped += c.polarity_flipped
            with_ctx += bool(c.context)
    print(f"{len(trials)} trials -> {total} criteria ({total / len(trials):.1f} per trial)")
    print(f"  polarity flipped by prose : {flipped}")
    print(f"  carrying parent context   : {with_ctx}")
