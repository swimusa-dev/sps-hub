"""Azure Functions entry points for the SPS analytics filing job.

Three functions, one parser:

  file_reports   timer, every 15 minutes, files newly arrived reports
  backfill       HTTP, admin-triggered, files a date range
  parse_preview  HTTP, dry parse of a subject line, no mailbox and no writes

`backfill` runs the same code as `file_reports`, so the two cannot drift.
That was the hard part to guarantee in the Power Automate design.
"""

from __future__ import annotations

import datetime as _dt
import json
import logging

import azure.functions as func

from sps_filing import plan_filing
from sps_filing.config import Settings
from sps_filing.filer import load_mapping, run
from sps_filing.graph import GraphClient
from sps_filing.models import Attachment, Message

app = func.FunctionApp()
log = logging.getLogger(__name__)


def _utcnow() -> _dt.datetime:
    return _dt.datetime.now(_dt.timezone.utc)


@app.timer_trigger(
    schedule="%SPS_SCHEDULE%", arg_name="timer", run_on_startup=False, use_monitor=True
)
def file_reports(timer: func.TimerRequest) -> None:
    settings = Settings.from_env()
    since = _utcnow() - _dt.timedelta(hours=settings.lookback_hours)
    client = GraphClient()
    try:
        summary = run(client, settings, since=since)
    finally:
        client.close()
    log.info("filing run complete: %s", json.dumps(summary.as_dict()))
    if summary.errors:
        # Surface to Application Insights so the alert rule fires.
        raise RuntimeError(f"{len(summary.errors)} message(s) failed to file")


@app.route(route="backfill", methods=["POST"], auth_level=func.AuthLevel.FUNCTION)
def backfill(req: func.HttpRequest) -> func.HttpResponse:
    """POST {"since": "2026-08-11", "until": "2026-08-31"}

    Chunk by month. The Inbox holds more messages than a single Graph page,
    and a smaller chunk means a bad parse is caught after 600 files rather
    than 1,001.
    """
    try:
        body = req.get_json()
        since = _dt.datetime.fromisoformat(body["since"]).replace(tzinfo=_dt.timezone.utc)
        until_raw = body.get("until")
        until = (
            _dt.datetime.fromisoformat(until_raw).replace(
                tzinfo=_dt.timezone.utc, hour=23, minute=59, second=59
            )
            if until_raw
            else None
        )
    except (ValueError, KeyError, TypeError) as exc:
        return func.HttpResponse(f"bad request: {exc}", status_code=400)

    settings = Settings.from_env()
    client = GraphClient()
    try:
        summary = run(client, settings, since=since, until=until)
    finally:
        client.close()
    return func.HttpResponse(
        json.dumps(summary.as_dict(), indent=2), mimetype="application/json"
    )


@app.route(route="parse", methods=["POST"], auth_level=func.AuthLevel.FUNCTION)
def parse_preview(req: func.HttpRequest) -> func.HttpResponse:
    """POST {"subject": "...", "received": "2026-09-14", "attachment": "x.xlsx"}

    Answers "where would this land?" without touching the mailbox or writing
    anything. This is what to use when adding a retailer to the mapping list:
    add the row, call this, confirm the path, then resubmit the real message.
    """
    body = req.get_json() or {}
    subject = body.get("subject", "")
    received_raw = body.get("received")
    received = (
        _dt.datetime.fromisoformat(received_raw).replace(tzinfo=_dt.timezone.utc)
        if received_raw
        else _utcnow()
    )
    attachment = body.get("attachment", "report.xlsx")

    settings = Settings.from_env()
    client = GraphClient()
    try:
        site_id = client.site_id(settings.sharepoint_hostname, settings.sharepoint_site_path)
        table = load_mapping(client, settings, site_id)
    finally:
        client.close()

    message = Message(
        subject=subject,
        sender=body.get("sender", "analytics@spscommerce.com"),
        received=received,
        internet_message_id="<preview@local>",
        attachments=(Attachment(name=attachment, size=250_000),),
    )
    result, plans = plan_filing(message, table, settings.library_root)
    return func.HttpResponse(
        json.dumps(
            {
                "disposition": result.disposition.value,
                "normalizedSubject": result.normalized_subject,
                "weekEnding": result.week_ending.isoformat(),
                "reasons": list(result.reasons),
                "plans": [
                    {"path": p.full_path, "metadata": p.metadata} for p in plans
                ],
            },
            indent=2,
        ),
        mimetype="application/json",
    )
