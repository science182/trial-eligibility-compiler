"""Calendar arithmetic for temporal predicates.

Washout windows are written in days, weeks, months, and years. Days and weeks
are exact multiples; months and years are NOT. Treating "6 months" as 180 days
drifts by up to 4 days depending on where the anchor falls, which is enough to
put a computed eligibility date on the wrong side of a clinic visit.

Months and years therefore use calendar arithmetic with end-of-month clamping,
the same convention clinical calendars use: 31 Jan + 1 month = 28 Feb (29 Feb in
a leap year), and 29 Feb + 1 year = 28 Feb.

No third-party dependency: dateutil is not in the stdlib and this is a handful
of lines.
"""

from calendar import monthrange
from datetime import date, timedelta

UNIT_ALIASES = {
    "day": "days", "days": "days",
    "week": "weeks", "weeks": "weeks", "wk": "weeks", "wks": "weeks",
    "month": "months", "months": "months", "mo": "months", "mos": "months",
    "year": "years", "years": "years", "yr": "years", "yrs": "years",
    "hour": "hours", "hours": "hours", "hr": "hours", "hrs": "hours",
}

# Nominal length in days. Used for ordering and display only -- never for the
# actual date computation when the unit is months or years.
NOMINAL_DAYS = {"hours": 1 / 24, "days": 1, "weeks": 7,
                "months": 30.4375, "years": 365.25}

EXACT_UNITS = {"hours", "days", "weeks"}


def normalize_unit(raw):
    """'wks' -> 'weeks'. Raises KeyError on an unknown unit rather than guessing."""
    return UNIT_ALIASES[raw.strip().lower().rstrip(".")]


def approx_days(amount, unit):
    """Nominal day count, for sorting and for the `days` display field."""
    return round(amount * NOMINAL_DAYS[normalize_unit(unit)], 2)


def add_months(anchor, months):
    """Add calendar months, clamping to the last valid day of the target month."""
    total = anchor.month - 1 + months
    year = anchor.year + total // 12
    month = total % 12 + 1
    day = min(anchor.day, monthrange(year, month)[1])
    return date(year, month, day)


def add_window(anchor, amount, unit):
    """Anchor date plus a washout window.

    >>> add_window(date(2026, 1, 31), 1, "months")
    datetime.date(2026, 2, 28)
    >>> add_window(date(2024, 1, 31), 1, "months")     # leap year
    datetime.date(2024, 2, 29)
    >>> add_window(date(2024, 2, 29), 1, "years")
    datetime.date(2025, 2, 28)
    """
    u = normalize_unit(unit)
    if u == "hours":
        # Sub-day precision is not tracked on patient dates; round up so the
        # window is never reported as shorter than the protocol requires.
        return anchor + timedelta(days=1 if amount else 0)
    if u == "days":
        return anchor + timedelta(days=amount)
    if u == "weeks":
        return anchor + timedelta(weeks=amount)
    if u == "months":
        return add_months(anchor, int(amount))
    if u == "years":
        return add_months(anchor, int(amount) * 12)
    raise ValueError(f"unhandled unit {unit!r}")
