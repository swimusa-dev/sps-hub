"""Retail calendar arithmetic.

Swim USA runs the NRF 4-5-4 calendar: weeks run Sunday through Saturday, and
the fiscal year ends on the Saturday closest to 31 January. A 53rd week falls
out every five or six years.

Everything downstream keys off `week_ending`, not the message received date.
That is what collapses a resend onto the same filename as the original and
keeps a weekly folder at one file per reporting week.
"""

from __future__ import annotations

import datetime as _dt

_SATURDAY = 5  # datetime.date.weekday(): Monday is 0, Saturday is 5.


def week_ending(day: _dt.date) -> _dt.date:
    """The Saturday that ends the reporting week containing `day`.

    Reports arrive Sunday through Tuesday for the week that just closed, so
    this resolves the most recent Saturday on or before `day`. A Sunday and a
    Monday delivery of the same report both land on the same Saturday, which
    is the whole point.
    """
    return day - _dt.timedelta(days=(day.weekday() - _SATURDAY) % 7)


def fiscal_year_end(year: int) -> _dt.date:
    """The Saturday closest to 31 January of `year`.

    This is the last day of fiscal year `year - 1`.
    """
    jan31 = _dt.date(year, 1, 31)
    candidates = (
        jan31 + _dt.timedelta(days=offset)
        for offset in range(-6, 7)
    )
    saturdays = [d for d in candidates if d.weekday() == _SATURDAY]
    return min(saturdays, key=lambda d: abs((d - jan31).days))


def fiscal_year_start(fiscal_year: int) -> _dt.date:
    """The Sunday on which `fiscal_year` begins."""
    return fiscal_year_end(fiscal_year) + _dt.timedelta(days=1)


def fiscal_year_weeks(fiscal_year: int) -> int:
    """52, or 53 in a long year."""
    start = fiscal_year_start(fiscal_year)
    end = fiscal_year_end(fiscal_year + 1)
    return ((end - start).days + 1) // 7


def fiscal_week(week_end: _dt.date) -> tuple[int, int]:
    """Return (fiscal_year, week_number) for a week-ending Saturday."""
    for candidate in (week_end.year - 1, week_end.year):
        start = fiscal_year_start(candidate)
        end = fiscal_year_end(candidate + 1)
        if start <= week_end <= end:
            return candidate, ((week_end - start).days // 7) + 1
    raise ValueError(f"{week_end} did not fall in a fiscal year")


def fiscal_week_label(week_end: _dt.date) -> str:
    """e.g. 2026-W32. Note this is the fiscal week, not the ISO week.

    ISO weeks start Monday and count from January, so they split this
    mailbox's Sunday and Monday deliveries across two different weeks and run
    about five ahead of the fiscal number.
    """
    year, week = fiscal_week(week_end)
    return f"{year}-W{week:02d}"
