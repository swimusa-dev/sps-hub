"""Behaviour tests: the rules that keep the library trustworthy."""

import datetime as _dt

from conftest import LIBRARY_ROOT, make_message
from sps_filing import plan_filing
from sps_filing.models import Attachment, Disposition

STYLE_SELLING = "1. SALES - CONTROL BRANDS DILLARDS STYLE SELLING To-Date Analysis"


def test_resend_resolves_to_the_same_filename(table):
    """The rule the 53-files-per-folder ceiling rests on.

    A correction resent the next day must overwrite, not accumulate. Received
    dates differ; the week-ending anchor does not.
    """
    original = make_message(STYLE_SELLING, _dt.date(2026, 9, 13), message_id="<a@sps>")
    resend = make_message(STYLE_SELLING, _dt.date(2026, 9, 14), message_id="<b@sps>")

    _, first = plan_filing(original, table, LIBRARY_ROOT)
    _, second = plan_filing(resend, table, LIBRARY_ROOT)

    assert first[0].full_path == second[0].full_path
    assert first[0].metadata["SourceMessageId"] != second[0].metadata["SourceMessageId"]


def test_parsing_is_deterministic(table):
    """Same input, same output, every time. No filename drift."""
    message = make_message(STYLE_SELLING, _dt.date(2026, 9, 14))
    runs = {plan_filing(message, table, LIBRARY_ROOT)[1][0].full_path for _ in range(25)}
    assert len(runs) == 1


def test_unroutable_subject_goes_to_unclassified(table):
    """`3. SALES - DOOR PERFORMANCE` carries no retailer and no brand."""
    message = make_message("3. SALES - DOOR PERFORMANCE", _dt.date(2026, 9, 14))
    result, plans = plan_filing(message, table, LIBRARY_ROOT)

    assert result.disposition is Disposition.UNCLASSIFIED
    assert "no retailer matched" in result.reasons
    assert plans[0].folder_path == f"{LIBRARY_ROOT}/_Unclassified/2026-09"
    # The subject is preserved so the weekly report can say what to add.
    assert plans[0].metadata["SourceSubject"] == "SALES DOOR PERFORMANCE"


def test_non_report_sender_goes_to_admin(table):
    message = make_message("Your SPS account", _dt.date(2026, 9, 14),
                           sender="no-reply@spscommerce.com")
    result, plans = plan_filing(message, table, LIBRARY_ROOT)
    assert result.disposition is Disposition.ADMIN
    assert plans[0].folder_path == f"{LIBRARY_ROOT}/_Admin/2026"


def test_unknown_sender_is_filed_not_discarded(table):
    """Nothing is ever silently dropped."""
    message = make_message("Something new", _dt.date(2026, 9, 14),
                           sender="stranger@example.com")
    result, plans = plan_filing(message, table, LIBRARY_ROOT)
    assert result.disposition is Disposition.ADMIN
    assert len(plans) == 1


def test_cross_retailer_does_not_pick_up_brand_ts(table):
    """TS appears inside ACCTS. Bounded matching must not see it."""
    message = make_message(
        "SALES - TOP 6 ACCTS ALL BRANDS TOTAL WTD MTD & STD To-Date Analysis",
        _dt.date(2026, 9, 14),
    )
    result, plans = plan_filing(message, table, LIBRARY_ROOT)

    assert result.retailer.output_code == "CROSS-RETAILER"
    assert result.brand_code != "TS"
    assert plans[0].folder_path.startswith(f"{LIBRARY_ROOT}/2026/_Cross-Retailer/")


def test_year_boundary_files_under_the_reporting_year(table):
    """A report arriving New Year's Day covers a 2025 week."""
    message = make_message(STYLE_SELLING, _dt.date(2026, 1, 1))
    _, plans = plan_filing(message, table, LIBRARY_ROOT)
    assert plans[0].folder_path.startswith(f"{LIBRARY_ROOT}/2025/")
    assert plans[0].file_name.startswith("2025-12-27_")


def test_inline_images_and_signature_graphics_are_skipped(table):
    """A report that is really a link, with only signature art attached."""
    message = make_message(STYLE_SELLING, _dt.date(2026, 9, 14), attachment=None)
    message = type(message)(
        subject=message.subject,
        sender=message.sender,
        received=message.received,
        internet_message_id=message.internet_message_id,
        attachments=(
            Attachment(name="logo.png", size=4_200, is_inline=True),
            Attachment(name="signature.gif", size=1_100),
            Attachment(name="tiny-logo.xlsx", size=900),
        ),
    )
    result, plans = plan_filing(message, table, LIBRARY_ROOT)

    assert result.disposition is Disposition.REPORT
    # No plans means the caller routes to _Unclassified/_Links and alerts.
    assert plans == []


def test_extension_comes_from_the_attachment(table):
    """Never hardcoded per family: it describes the bytes actually sent."""
    for name, expected in [("x.txt", ".txt"), ("x.csv", ".csv"), ("x.XLSX", ".xlsx")]:
        message = make_message("DILLARDS Qlik Sell Thru Sales Report RL",
                               _dt.date(2026, 9, 14), attachment=name)
        _, plans = plan_filing(message, table, LIBRARY_ROOT)
        assert plans[0].file_name.endswith(expected)


def test_metadata_carries_the_audit_trail(table):
    message = make_message(STYLE_SELLING, _dt.date(2026, 9, 14),
                           attachment="1. SALES - CONTROL BRANDS DILLARDS.xlsx")
    _, plans = plan_filing(message, table, LIBRARY_ROOT)
    meta = plans[0].metadata

    assert meta["Retailer"] == "DILLARDS"
    assert meta["Brand"] == "CONTROL-BRANDS"
    assert meta["ReportFamily"] == "STYLE-SELLING"
    assert meta["WeekEnding"] == "2026-09-12"
    assert meta["FiscalWeek"] == "2026-W32"
    assert meta["SourceAttachmentName"] == "1. SALES - CONTROL BRANDS DILLARDS.xlsx"
    assert meta["ParseConflict"] is False


def test_every_audited_family_routes(table):
    """A smoke pass over one subject per report family."""
    subjects = [
        "DILLARDS Qlik Sell Thru Sales Report MG",
        "SPS RETURNS REPORT - KOHLS Weekly Trend Analysis",
        "SALES - ALL DIVISIONS - BELK WTD MTD & STD To-Date Analysis",
        "4. SALES - SWIM SOLUTIONS MACYS by Door & Style Performance to Date",
        "1. SALES - LONGITUDE DILLARDS STYLE SELLING To-Date Analysis",
        "2. SALES - VITAMIN A NORDSTROM Weekly Trend Analysis",
        "3. SALES - POLO SAKS WTD, MTD & STD To-Date Analysis",
    ]
    for subject in subjects:
        message = make_message(subject, _dt.date(2026, 9, 14))
        result, plans = plan_filing(message, table, LIBRARY_ROOT)
        assert result.disposition is Disposition.REPORT, (subject, result.reasons)
        assert len(plans) == 1
