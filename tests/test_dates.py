"""Date arithmetic tests. Section 10 requires month boundaries and leap years."""

import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dates import add_months, add_window, approx_days, normalize_unit  # noqa: E402


class TestExactUnits:
    def test_days(self):
        assert add_window(date(2026, 1, 1), 28, "days") == date(2026, 1, 29)

    def test_weeks(self):
        assert add_window(date(2026, 1, 1), 4, "weeks") == date(2026, 1, 29)

    def test_days_and_weeks_agree(self):
        anchor = date(2026, 3, 15)
        assert add_window(anchor, 28, "days") == add_window(anchor, 4, "weeks")


class TestMonthBoundaries:
    @pytest.mark.parametrize("anchor,months,expected", [
        (date(2026, 1, 31), 1, date(2026, 2, 28)),   # clamp to short month
        (date(2026, 1, 30), 1, date(2026, 2, 28)),
        (date(2026, 1, 29), 1, date(2026, 2, 28)),
        (date(2026, 1, 28), 1, date(2026, 2, 28)),   # exact, no clamp
        (date(2026, 3, 31), 1, date(2026, 4, 30)),
        (date(2026, 5, 31), 1, date(2026, 6, 30)),
        (date(2026, 8, 31), 6, date(2027, 2, 28)),   # crosses a year
        (date(2026, 12, 31), 1, date(2027, 1, 31)),
    ])
    def test_end_of_month_clamping(self, anchor, months, expected):
        assert add_window(anchor, months, "months") == expected

    def test_year_rollover(self):
        assert add_window(date(2026, 11, 15), 3, "months") == date(2027, 2, 15)

    def test_thirty_day_approximation_would_be_wrong(self):
        # 6 months from 31 Aug is 28 Feb, not 27 Feb (180 days).
        anchor = date(2026, 8, 31)
        assert add_window(anchor, 6, "months") == date(2027, 2, 28)
        assert add_window(anchor, 6, "months") != anchor + __import__(
            "datetime").timedelta(days=180)


class TestLeapYears:
    def test_jan_31_plus_one_month_in_leap_year(self):
        assert add_window(date(2024, 1, 31), 1, "months") == date(2024, 2, 29)

    def test_feb_29_plus_one_year_clamps(self):
        assert add_window(date(2024, 2, 29), 1, "years") == date(2025, 2, 28)

    def test_feb_29_plus_four_years_is_leap_again(self):
        assert add_window(date(2024, 2, 29), 4, "years") == date(2028, 2, 29)

    def test_window_spanning_leap_day_in_days(self):
        assert add_window(date(2024, 2, 27), 3, "days") == date(2024, 3, 1)
        assert add_window(date(2025, 2, 27), 3, "days") == date(2025, 3, 2)

    def test_one_year_across_a_leap_day(self):
        assert add_window(date(2023, 3, 1), 1, "years") == date(2024, 3, 1)


class TestUnitNormalization:
    @pytest.mark.parametrize("raw,expected", [
        ("day", "days"), ("days", "days"), ("Week", "weeks"), ("wks", "weeks"),
        ("month", "months"), ("mos", "months"), ("yr", "years"),
    ])
    def test_aliases(self, raw, expected):
        assert normalize_unit(raw) == expected

    def test_unknown_unit_raises(self):
        with pytest.raises(KeyError):
            normalize_unit("fortnights")

    def test_approx_days_is_nominal_only(self):
        assert approx_days(4, "weeks") == 28
        assert approx_days(1, "days") == 1
        assert 182 < approx_days(6, "months") < 183


class TestAddMonthsDirect:
    def test_zero_is_identity(self):
        assert add_months(date(2026, 5, 17), 0) == date(2026, 5, 17)

    def test_twelve_months_is_one_year(self):
        assert add_months(date(2026, 5, 17), 12) == date(2027, 5, 17)
