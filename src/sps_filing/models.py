"""Data shapes shared across the parser."""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field
from enum import Enum


class MapType(str, Enum):
    SENDER = "Sender"
    RETAILER = "Retailer"
    REPORT_FAMILY = "ReportFamily"
    BRAND = "Brand"
    CALENDAR = "Calendar"


class MatchMode(str, Enum):
    TOKEN = "Token"
    ENDS_WITH = "EndsWith"


class Disposition(str, Enum):
    REPORT = "report"
    ADMIN = "admin"
    UNCLASSIFIED = "unclassified"


@dataclass(frozen=True)
class MappingRow:
    """One row of the SPS Filing Map list.

    `priority` decides ties: higher wins. For retailers and brands it is the
    token's character count, so SHAPE SOLVER SPORT beats SHAPE SOLVER. For
    report families it is an explicit specificity ranking, because length
    gives the wrong answer: SPS RETURNS REPORT must beat WEEKLY TREND
    ANALYSIS, and it is the shorter of the two.
    """

    title: str
    map_type: MapType
    output_code: str = ""
    folder_name: str = ""
    match_mode: MatchMode = MatchMode.TOKEN
    match_token_2: str = ""
    priority: int = 0
    default_brand: str = ""
    default_brand_folder: str = ""
    cadence: str = "Weekly"
    qlik_only: bool = False
    active: bool = True


@dataclass(frozen=True)
class Attachment:
    name: str
    content_type: str = ""
    size: int = 0
    is_inline: bool = False
    content_id: str = ""


@dataclass(frozen=True)
class Message:
    subject: str
    sender: str
    received: _dt.datetime
    internet_message_id: str
    message_id: str = ""
    attachments: tuple[Attachment, ...] = ()


@dataclass(frozen=True)
class ParseResult:
    """What the subject line resolved to, before any file is named."""

    disposition: Disposition
    normalized_subject: str
    week_ending: _dt.date
    retailer: MappingRow | None = None
    family: MappingRow | None = None
    brand: MappingRow | None = None
    calendar: MappingRow | None = None
    reasons: tuple[str, ...] = ()

    @property
    def brand_code(self) -> str:
        if self.brand is not None:
            return self.brand.output_code
        return self.family.default_brand if self.family else ""

    @property
    def brand_folder(self) -> str:
        if self.brand is not None:
            return self.brand.folder_name
        return self.family.default_brand_folder if self.family else ""


@dataclass
class FilePlan:
    """Where one attachment goes, and what metadata rides with it."""

    folder_path: str
    file_name: str
    attachment: Attachment
    metadata: dict = field(default_factory=dict)

    @property
    def full_path(self) -> str:
        return f"{self.folder_path}/{self.file_name}"
