"""The normalization rules, and the live subjects that motivate each one."""

import pytest

from sps_filing.normalize import contains_token, normalize_subject, normalize_token


@pytest.mark.parametrize(
    "raw, expected",
    [
        # Apostrophes are stripped, not spaced, or MACY'S stops matching MACYS.
        ("1. SALES - SALT & COVE MACY'S STYLE SELLING",
         "SALES SALT & COVE MACYS STYLE SELLING"),
        ("SALES - MACY’S STYLE SELLING", "SALES MACYS STYLE SELLING"),
        # Non-ASCII corruption, present in at least six recurring subjects.
        ("3. SALES -� S3 KOHLS WTD, MTD & STD To-Date Analysis",
         "SALES S3 KOHLS WTD MTD & STD TO DATE ANALYSIS"),
        # Missing space after the hyphen.
        ("2. SALES - MIMI SIGNATURE- MAYCS Weekly Trend Analysis",
         "SALES MIMI SIGNATURE MAYCS WEEKLY TREND ANALYSIS"),
        # Doubled internal spaces, and comma-free WTD,MTD,STD.
        ("3. SALES - LAUREN MISSY DILLARDS  WTD,MTD,STD To-Date Analysis",
         "SALES LAUREN MISSY DILLARDS WTD MTD STD TO DATE ANALYSIS"),
        ("", ""),
        (None, ""),
    ],
)
def test_normalize_subject(raw, expected):
    assert normalize_subject(raw) == expected


def test_ampersand_survives():
    """& is a real token separator in SALT & COVE and DOOR & STYLE."""
    assert normalize_token("Salt & Cove") == "SALT & COVE"


def test_token_keeps_leading_digits():
    """Rule 5 applies to subjects only.

    Applying it to tokens would shorten 4 5 4 CALENDAR to 5 4 CALENDAR and
    every Macys 4-5-4 rollup would silently lose its calendar segment.
    """
    assert normalize_token("4-5-4 Calendar") == "4 5 4 CALENDAR"
    assert normalize_subject("4-5-4 Calendar") == "5 4 CALENDAR"


def test_bounded_matching_rejects_substrings():
    """The case a naive `contains` gets wrong every single week."""
    assert not contains_token("SALES TOP 6 ACCTS ROLLUP", "TS")
    assert contains_token("DILLARDS QLIK SELL THRU SALES REPORT TS", "TS")
