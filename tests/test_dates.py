"""Retail calendar arithmetic."""

import datetime as _dt

import pytest

from sps_filing.dates import (
    fiscal_week,
    fiscal_week_label,
    fiscal_year_end,
    fiscal_year_start,
    fiscal_year_weeks,
    week_ending,
)


@pytest.mark.parametrize(
    "received, expected",
    [
        (_dt.date(2026, 9, 12), _dt.date(2026, 9, 12)),  # Saturday itself
        (_dt.date(2026, 9, 13), _dt.date(2026, 9, 12)),  # Sunday
        (_dt.date(2026, 9, 14), _dt.date(2026, 9, 12)),  # Monday
        (_dt.date(2026, 9, 8), _dt.date(2026, 9, 5)),    # Tuesday
        (_dt.date(2026, 1, 1), _dt.date(2025, 12, 27)),  # crosses the year
    ],
)
def test_week_ending(received, expected):
    assert week_ending(received) == expected


def test_sunday_and_monday_share_a_week():
    """The case that makes the resend rule work, and that ISO weeks get wrong."""
    assert week_ending(_dt.date(2026, 9, 13)) == week_ending(_dt.date(2026, 9, 14))
    assert _dt.date(2026, 9, 13).isocalendar().week != _dt.date(2026, 9, 14).isocalendar().week


@pytest.mark.parametrize(
    "fiscal_year, start, end, weeks",
    [
        (2025, _dt.date(2025, 2, 2), _dt.date(2026, 1, 31), 52),
        (2026, _dt.date(2026, 2, 1), _dt.date(2027, 1, 30), 52),
        (2027, _dt.date(2027, 1, 31), _dt.date(2028, 1, 29), 52),
        (2028, _dt.date(2028, 1, 30), _dt.date(2029, 2, 3), 53),
    ],
)
def test_fiscal_year_bounds(fiscal_year, start, end, weeks):
    assert fiscal_year_start(fiscal_year) == start
    assert fiscal_year_end(fiscal_year + 1) == end
    assert fiscal_year_weeks(fiscal_year) == weeks


def test_fifty_three_week_years_land_every_five_or_six():
    long_years = [y for y in range(2020, 2041) if fiscal_year_weeks(y) == 53]
    assert long_years == [2023, 2028, 2034, 2040]
    gaps = {b - a for a, b in zip(long_years, long_years[1:])}
    assert gaps <= {5, 6}


def test_fiscal_week_is_not_the_iso_week():
    """The spec's example said 2026-W37; under 4-5-4 it is 2026-W32."""
    assert fiscal_week(_dt.date(2026, 9, 12)) == (2026, 32)
    assert fiscal_week_label(_dt.date(2026, 9, 12)) == "2026-W32"
    assert _dt.date(2026, 9, 12).isocalendar().week == 37


def test_no_week_ending_falls_outside_a_fiscal_year():
    day = _dt.date(2024, 1, 1)
    while day < _dt.date(2031, 1, 1):
        fiscal_week(week_ending(day))
        day += _dt.timedelta(days=1)
