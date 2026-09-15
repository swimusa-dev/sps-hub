"""Turn a parsed message into concrete SharePoint paths and metadata."""

from __future__ import annotations

import datetime as _dt
import re
from pathlib import PurePosixPath
from zoneinfo import ZoneInfo

from .dates import fiscal_week_label
from .mapping import MappingTable
from .models import Attachment, Disposition, FilePlan, Message, ParseResult
from .parse import MAILBOX_TZ, local_received, parse_message

#: Extensions SPS actually sends. Anything else is treated as not a report.
REPORT_EXTENSIONS = frozenset({"xlsx", "xls", "csv", "txt", "pdf", "zip"})

#: Below this, an attachment is a signature graphic or a tracking pixel rather
#: than a report. Comfortably under the smallest real workbook.
MIN_REPORT_BYTES = 15_000

#: A leading YYYY-MM-DD in the attachment name. Inert against the current feed:
#: zero of the 1,001 audited attachments carry a date. Kept so a future sender
#: that names files properly is honoured without a code change.
_SORTABLE_DATE = re.compile(r"^(\d{4}-\d{2}-\d{2})")

_UNSAFE = re.compile(r"[^A-Za-z0-9 &._-]")


def extension_of(name: str) -> str:
    return PurePosixPath(name).suffix.lstrip(".").lower()


def is_report_attachment(attachment: Attachment) -> bool:
    """Filter out inline images, signature graphics and stray file types.

    `is_inline` catches images embedded in the body. The size floor catches
    signature logos that arrive as real attachments instead, which `is_inline`
    does not flag.
    """
    if attachment.is_inline:
        return False
    if attachment.size and attachment.size < MIN_REPORT_BYTES:
        return False
    return extension_of(attachment.name) in REPORT_EXTENSIONS


def date_stamp(
    result: ParseResult,
    attachment: Attachment,
    *,
    prefer_attachment_date: bool = False,
) -> str:
    """The sortable date segment of the filename.

    Three cases, in the order the business rule states them: preserve an
    existing sortable date, otherwise derive one. Deriving means the
    week-ending Saturday, which is the report's period rather than the
    accident of when it was delivered.

    `prefer_attachment_date` is off by default. Nothing in the current feed
    carries a date, so leaving it on would mean shipping an untested branch
    that fires unpredictably.
    """
    if prefer_attachment_date:
        match = _SORTABLE_DATE.match(attachment.name)
        if match:
            return match.group(1)
    monthly = result.family is not None and result.family.cadence.lower() == "monthly"
    return result.week_ending.strftime("%Y-%m" if monthly else "%Y-%m-%d")


def _safe(fragment: str, limit: int = 80) -> str:
    """Make a subject fragment usable as a filename.

    Only ever applied to unclassified items, whose names come from subject
    text rather than the controlled mapping list. SharePoint enforces a
    400-character total URL limit; the truncation keeps the longest possible
    unclassified path well inside it.
    """
    cleaned = _UNSAFE.sub("", fragment).strip().replace(" ", "-")
    return cleaned[:limit].strip("-") or "UNTITLED"


def build_filename(
    result: ParseResult,
    attachment: Attachment,
    *,
    prefer_attachment_date: bool = False,
) -> str:
    """`{YYYY-MM-DD}_{RETAILER}_{BRAND}_{REPORT}[_{CALENDAR}].{ext}`"""
    parts = [
        date_stamp(result, attachment, prefer_attachment_date=prefer_attachment_date),
        result.retailer.output_code if result.retailer else "UNKNOWN",
        result.brand_code or "ALL-BRANDS",
        result.family.output_code if result.family else "UNKNOWN",
    ]
    if result.calendar is not None and result.calendar.output_code:
        parts.append(result.calendar.output_code)
    return "_".join(parts) + f".{extension_of(attachment.name)}"


def build_folder_path(result: ParseResult, library_root: str) -> str:
    """Year, retailer, report family, brand. Four levels below the root.

    The year is the calendar year of the week-ending date, not the fiscal
    year, so the folder and the filename always agree. The fiscal view is
    served by the FiscalWeek column instead.
    """
    root = library_root.rstrip("/")
    if result.disposition is Disposition.ADMIN:
        return f"{root}/_Admin/{result.week_ending:%Y}"
    if result.disposition is Disposition.UNCLASSIFIED:
        return f"{root}/_Unclassified/{result.week_ending:%Y-%m}"
    return "/".join(
        [
            root,
            f"{result.week_ending:%Y}",
            result.retailer.folder_name,
            result.family.folder_name,
            result.brand_folder,
        ]
    )


def build_metadata(message: Message, result: ParseResult, attachment: Attachment) -> dict:
    received = local_received(message.received)
    meta = {
        "ReceivedDate": received.isoformat(),
        "WeekEnding": result.week_ending.isoformat(),
        "FiscalWeek": fiscal_week_label(result.week_ending),
        "SourceSubject": result.normalized_subject,
        "SourceMessageId": message.internet_message_id,
        "SourceAttachmentName": attachment.name,
        "ParseConflict": result.disposition is not Disposition.REPORT,
    }
    if result.disposition is Disposition.REPORT:
        meta["Retailer"] = result.retailer.output_code
        meta["Brand"] = result.brand_code
        meta["ReportFamily"] = result.family.output_code
        meta["Calendar"] = result.calendar.output_code if result.calendar else ""
    return meta


def plan_filing(
    message: Message,
    table: MappingTable,
    library_root: str,
    *,
    tz: ZoneInfo = MAILBOX_TZ,
    prefer_attachment_date: bool = False,
) -> tuple[ParseResult, list[FilePlan]]:
    """Where every attachment on this message should be written.

    Returns the parse result alongside the plans so callers can act on an
    empty plan list, which means the report arrived as a link or body text
    rather than a file.
    """
    result = parse_message(message, table, tz=tz)
    folder = build_folder_path(result, library_root)
    reportable = [a for a in message.attachments if is_report_attachment(a)]

    plans: list[FilePlan] = []
    for attachment in reportable:
        if result.disposition is Disposition.REPORT:
            name = build_filename(
                result, attachment, prefer_attachment_date=prefer_attachment_date
            )
        else:
            stamp = result.week_ending.isoformat()
            name = f"{stamp}_{_safe(result.normalized_subject)}_{_safe(attachment.name, 60)}"
        plans.append(
            FilePlan(
                folder_path=folder,
                file_name=name,
                attachment=attachment,
                metadata=build_metadata(message, result, attachment),
            )
        )
    return result, plans
