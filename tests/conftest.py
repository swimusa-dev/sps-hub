import datetime as _dt
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from sps_filing.mapping import load_csv
from sps_filing.models import Attachment, Message

SEED = Path(__file__).resolve().parents[1] / "data" / "sps_filing_map_seed.csv"
EASTERN = ZoneInfo("America/New_York")
LIBRARY_ROOT = "/Shared Documents/02 - Sales/05 - Published Reports"
REPORT_SENDER = "analytics@spscommerce.com"


@pytest.fixture(scope="session")
def table():
    return load_csv(SEED)


def make_message(subject, received_date, *, sender=REPORT_SENDER,
                 attachment="report.xlsx", size=250_000, message_id=None):
    """A message received mid-morning Eastern on `received_date`."""
    received = _dt.datetime.combine(
        received_date, _dt.time(9, 30), tzinfo=EASTERN
    ).astimezone(_dt.timezone.utc)
    attachments = ()
    if attachment is not None:
        attachments = (Attachment(name=attachment, size=size),)
    return Message(
        subject=subject,
        sender=sender,
        received=received,
        internet_message_id=message_id or f"<{abs(hash(subject))}@spscommerce.com>",
        attachments=attachments,
    )
