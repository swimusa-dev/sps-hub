"""Parse SPS Commerce analytics report emails into a SharePoint filing plan.

The public entry point is `plan_filing`, which is a pure function: given a
message, its attachments and the mapping table, it returns where every
attachment should be written and with what metadata. It performs no I/O.
"""

from .models import Attachment, Disposition, FilePlan, Message, ParseResult
from .plan import plan_filing

__all__ = [
    "Attachment",
    "Disposition",
    "FilePlan",
    "Message",
    "ParseResult",
    "plan_filing",
]
