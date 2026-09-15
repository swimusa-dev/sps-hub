"""Orchestration: read the mailbox, plan, write to SharePoint.

All the I/O lives here. Everything it decides comes from `plan_filing`, which
is pure, so the interesting logic stays testable without a tenant.
"""

from __future__ import annotations

import base64
import datetime as _dt
import logging
from dataclasses import dataclass, field

from .config import Settings
from .graph import GraphClient, GraphError
from .mapping import MappingTable, row_from_dict
from .models import Attachment, Disposition, Message
from .plan import _safe, is_report_attachment
from .plan import plan_filing

log = logging.getLogger(__name__)

FILE_ATTACHMENT = "#microsoft.graph.fileAttachment"


@dataclass
class RunSummary:
    examined: int = 0
    created: int = 0
    replaced: int = 0
    skipped_duplicate: int = 0
    unclassified: int = 0
    admin: int = 0
    link_only: int = 0
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "examined": self.examined,
            "created": self.created,
            "replaced": self.replaced,
            "skippedDuplicate": self.skipped_duplicate,
            "unclassified": self.unclassified,
            "admin": self.admin,
            "linkOnly": self.link_only,
            "errors": self.errors,
        }


def load_mapping(client: GraphClient, settings: Settings, site_id: str) -> MappingTable:
    rows = [row_from_dict(fields) for fields in client.list_items(site_id, settings.mapping_list)]
    log.info("loaded %d mapping rows", len(rows))
    return MappingTable(rows)


def _to_message(raw: dict, attachments: list[dict]) -> Message:
    return Message(
        subject=raw.get("subject") or "",
        sender=(raw.get("from") or {}).get("emailAddress", {}).get("address", ""),
        received=_dt.datetime.fromisoformat(raw["receivedDateTime"].replace("Z", "+00:00")),
        internet_message_id=raw.get("internetMessageId") or "",
        message_id=raw["id"],
        attachments=tuple(
            Attachment(
                name=a.get("name") or "",
                content_type=a.get("contentType") or "",
                size=int(a.get("size") or 0),
                is_inline=bool(a.get("isInline")),
                content_id=a.get("contentId") or "",
            )
            for a in attachments
            if a.get("@odata.type") == FILE_ATTACHMENT
        ),
    )


def _content_for(attachments: list[dict], name: str) -> bytes:
    for raw in attachments:
        if raw.get("name") == name and raw.get("contentBytes"):
            return base64.b64decode(raw["contentBytes"])
    raise KeyError(f"no content for attachment {name!r}")


def process_message(
    client: GraphClient,
    settings: Settings,
    table: MappingTable,
    drive_id: str,
    raw: dict,
    summary: RunSummary,
) -> None:
    attachments = client.list_attachments(settings.mailbox, raw["id"])
    message = _to_message(raw, attachments)
    result, plans = plan_filing(message, table, settings.library_root)

    if result.disposition is Disposition.UNCLASSIFIED:
        summary.unclassified += 1
    elif result.disposition is Disposition.ADMIN:
        summary.admin += 1

    if not plans and result.disposition is Disposition.REPORT:
        # A real report with no file on it: a portal link, or body content.
        # Preserve the message itself so a human has the link in context.
        summary.link_only += 1
        folder = f"{settings.library_root}/_Unclassified/{result.week_ending:%Y-%m}/_Links"
        name = f"{result.week_ending:%Y-%m-%d}_{_safe(result.normalized_subject)}.eml"
        if not settings.dry_run:
            client.upload(drive_id, f"{folder}/{name}",
                          client.message_mime(settings.mailbox, message.message_id))
        log.warning("no report attachment on %r, filed the message to %s", message.subject, folder)
        return

    for plan in plans:
        existing = client.find_item_by_path(drive_id, plan.full_path)
        if existing is not None:
            fields = client.item_fields(drive_id, existing["id"])
            if fields.get("SourceMessageId") == message.internet_message_id:
                # Same message seen twice: a replay or a backfill overlap.
                summary.skipped_duplicate += 1
                continue
        if settings.dry_run:
            log.info("[dry run] would write %s", plan.full_path)
            continue
        item = client.upload(drive_id, plan.full_path, _content_for(attachments, plan.attachment.name))
        client.set_fields(drive_id, item["id"], plan.metadata)
        if existing is None:
            summary.created += 1
        else:
            # A different message resolving to the same name is a resend or a
            # correction. Overwriting creates a version; the folder count,
            # and so the 53-per-year ceiling, is untouched.
            summary.replaced += 1


def run(
    client: GraphClient,
    settings: Settings,
    *,
    since: _dt.datetime,
    until: _dt.datetime | None = None,
) -> RunSummary:
    summary = RunSummary()
    site_id = client.site_id(settings.sharepoint_hostname, settings.sharepoint_site_path)
    drive_id = client.drive_id(site_id, settings.library_name)
    table = load_mapping(client, settings, site_id)

    for raw in client.list_inbox_messages(settings.mailbox, since, until):
        summary.examined += 1
        try:
            process_message(client, settings, table, drive_id, raw, summary)
        except (GraphError, KeyError, ValueError) as exc:
            # One bad message must never stop the run. It stays in the mailbox
            # and the next pass picks it up again.
            detail = f"{raw.get('internetMessageId', raw['id'])}: {exc}"
            summary.errors.append(detail)
            log.exception("failed to file message %s", detail)
    return summary
