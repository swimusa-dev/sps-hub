"""Resolve a subject line to retailer, report family, brand and calendar.

Pure and deterministic. The same subject always yields the same result, which
is what the one-file-per-reporting-week rule depends on: if the filename
wobbled between runs, a resend would land beside the original instead of
replacing it.
"""

from __future__ import annotations

import datetime as _dt
from zoneinfo import ZoneInfo

from .dates import week_ending
from .mapping import MappingTable
from .models import Disposition, MappingRow, MapType, Message, ParseResult
from .normalize import normalize_subject, pad

MAILBOX_TZ = ZoneInfo("America/New_York")
QLIK_FAMILY = "QLIK-SELL-THRU"


def local_received(received: _dt.datetime, tz: ZoneInfo = MAILBOX_TZ) -> _dt.datetime:
    """Message receipt in the mailbox's own timezone.

    Graph returns UTC. A report received 21:30 Eastern on a Saturday is
    Sunday in UTC, which would push it into the following reporting week.
    """
    if received.tzinfo is None:
        received = received.replace(tzinfo=_dt.timezone.utc)
    return received.astimezone(tz)


def _sender_disposition(table: MappingTable, sender: str) -> str:
    wanted = (sender or "").strip().lower()
    for row in table.of(MapType.SENDER):
        if row.title.strip().lower() == wanted:
            return row.output_code.upper()
    # An unrecognised sender is filed to _Admin, never discarded.
    return "ADMIN"


def _subject_for_brand(subject: str, *tokens: str) -> str:
    """Subject with the retailer and family tokens removed.

    ALL DIVISIONS is both a family trigger and a brand. Removing the family
    token first stops it matching twice and lets the family's DefaultBrand
    apply instead.
    """
    padded = pad(subject)
    for token in tokens:
        if token:
            padded = padded.replace(pad(token), " ")
    return padded.strip()


def parse_message(
    message: Message,
    table: MappingTable,
    *,
    tz: ZoneInfo = MAILBOX_TZ,
) -> ParseResult:
    normalized = normalize_subject(message.subject)
    received = local_received(message.received, tz)
    ending = week_ending(received.date())

    if _sender_disposition(table, message.sender) != "REPORT":
        return ParseResult(
            disposition=Disposition.ADMIN,
            normalized_subject=normalized,
            week_ending=ending,
            reasons=(f"sender {message.sender!r} is not a report sender",),
        )

    retailer = table.best_match(MapType.RETAILER, normalized)
    family = table.best_match(MapType.REPORT_FAMILY, normalized)
    calendar = table.best_match(MapType.CALENDAR, normalized)

    brand: MappingRow | None = None
    if family is not None:
        brand_subject = _subject_for_brand(
            normalized,
            retailer.title if retailer else "",
            family.title,
        )
        is_qlik = family.output_code == QLIK_FAMILY
        brand = table.best_match(
            MapType.BRAND,
            brand_subject,
            predicate=lambda row: is_qlik if row.qlik_only else True,
        )

    reasons: list[str] = []
    if retailer is None:
        reasons.append("no retailer matched")
    if family is None:
        reasons.append("no report family matched")
    elif brand is None and not family.default_brand:
        reasons.append(f"no brand matched and family {family.output_code} has no default")

    disposition = Disposition.UNCLASSIFIED if reasons else Disposition.REPORT
    return ParseResult(
        disposition=disposition,
        normalized_subject=normalized,
        week_ending=ending,
        retailer=retailer,
        family=family,
        brand=brand,
        calendar=calendar,
        reasons=tuple(reasons),
    )
