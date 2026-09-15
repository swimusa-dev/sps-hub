"""The nine-subject parser trace table, as executable acceptance tests.

Every subject here is a real one from the mailbox audit. Each row exercises a
specific rule, named in the `rule` field, so a failure says what broke rather
than just which string did.
"""

import datetime as _dt

import pytest

from conftest import LIBRARY_ROOT, make_message
from sps_filing import plan_filing
from sps_filing.models import Disposition

# subject, received, expected folder below the year, expected filename, rule
TRACE_TABLE = [
    (
        "1. SALES - CONTROL BRANDS DILLARDS STYLE SELLING To-Date Analysis SUPPLIER",
        _dt.date(2026, 9, 14),
        "2026/Dillards/01 Style Selling/Control Brands",
        "2026-09-12_DILLARDS_CONTROL-BRANDS_STYLE-SELLING_SUPPLIER.xlsx",
        "trailing calendar token",
    ),
    (
        "DILLARDS Qlik Sell Thru Sales Report RL",
        _dt.date(2026, 9, 14),
        "2026/Dillards/06 Qlik Sell Thru/RL",
        "2026-09-12_DILLARDS_RL_QLIK-SELL-THRU.txt",
        "brand code the attachment does not carry",
    ),
    (
        "4. SALES - MIRACLESUIT MACYS by Door & Style Performance to Date",
        _dt.date(2026, 9, 13),
        "2026/Macys/05 Door and Style/Miraclesuit",
        "2026-09-12_MACYS_MIRACLESUIT_DOOR-AND-STYLE.xlsx",
        "multi-word family token containing &",
    ),
    (
        "SALES - ALL DIVISIONS - MACYS WTD MTD STD & YTD 4-5-4 Calendar To-Date Analysis",
        _dt.date(2026, 9, 13),
        "2026/Macys/08 Division Rollups/All Divisions",
        "2026-09-12_MACYS_ALL-DIVISIONS_ROLLUP_454.xlsx",
        "ALL DIVISIONS outranks WTD/STD, and the 4-5-4 calendar survives",
    ),
    (
        "SPS RETURNS REPORT - DILLARDS Weekly Trend Analysis",
        _dt.date(2026, 9, 14),
        "2026/Dillards/07 Returns/All Brands",
        "2026-09-12_DILLARDS_ALL-BRANDS_RETURNS.xlsx",
        "specificity beats length: RETURNS over WEEKLY TREND",
    ),
    (
        "2. SALES - MIMI SIGNATURE- MAYCS Weekly Trend Analysis",
        _dt.date(2026, 9, 14),
        "2026/Macys/02 Weekly Trend/Mimi Signature",
        "2026-09-12_MACYS_MIMI-SIGNATURE_WEEKLY-TREND.xlsx",
        "MAYCS typo alias, and a missing space after the hyphen",
    ),
    (
        "3. SALES -� S3 KOHLS WTD, MTD & STD To-Date Analysis",
        _dt.date(2026, 9, 14),
        "2026/Kohls/03 Period To-Date/S3",
        "2026-09-12_KOHLS_S3_PERIOD-TO-DATE.xlsx",
        "non-ASCII corruption, plus the two-character brand S3",
    ),
    (
        "SALES - CONTROL BRANDS - DILLARDS WTD MTD STD & YTD To-Date Analysis NRF",
        _dt.date(2026, 9, 8),
        "2026/Dillards/03 Period To-Date/Control Brands",
        "2026-09-05_DILLARDS_CONTROL-BRANDS_PERIOD-TO-DATE_NRF.xlsx",
        "trailing NRF calendar, and a Tuesday receipt",
    ),
    (
        "3. SALES - LAUREN MISSY DILLARDS  WTD,MTD,STD To-Date Analysis",
        _dt.date(2026, 9, 14),
        "2026/Dillards/03 Period To-Date/Lauren Missy",
        "2026-09-12_DILLARDS_LAUREN-MISSY_PERIOD-TO-DATE.xlsx",
        "doubled spaces, and LAUREN MISSY outranking LAUREN",
    ),
]


@pytest.mark.parametrize(
    "subject, received, folder, filename, rule",
    TRACE_TABLE,
    ids=[row[4] for row in TRACE_TABLE],
)
def test_trace_table(table, subject, received, folder, filename, rule):
    extension = filename.rsplit(".", 1)[1]
    message = make_message(subject, received, attachment=f"whatever.{extension}")
    result, plans = plan_filing(message, table, LIBRARY_ROOT)

    assert result.disposition is Disposition.REPORT, result.reasons
    assert len(plans) == 1
    assert plans[0].folder_path == f"{LIBRARY_ROOT}/{folder}"
    assert plans[0].file_name == filename
