"""The mapping table: loading it, and matching against it.

The table lives in a SharePoint list so the analytics team can add a retailer
without anyone touching code. This module never fetches it; callers pass rows
in. That keeps the parser pure and lets the tests drive it from a CSV.
"""

from __future__ import annotations

import csv
from collections.abc import Iterable, Sequence
from pathlib import Path

from .models import MappingRow, MapType, MatchMode
from .normalize import contains_token, normalize_token

_TRUE = {"yes", "true", "1", "y"}


def _flag(value: str | None) -> bool:
    return (value or "").strip().lower() in _TRUE


class MappingTable:
    """Rows grouped by type and pre-sorted by descending priority."""

    def __init__(self, rows: Iterable[MappingRow]) -> None:
        self._by_type: dict[MapType, list[MappingRow]] = {t: [] for t in MapType}
        for row in rows:
            if row.active:
                self._by_type[row.map_type].append(row)
        for bucket in self._by_type.values():
            bucket.sort(key=lambda r: (-r.priority, r.title))

    def of(self, map_type: MapType) -> Sequence[MappingRow]:
        return self._by_type[map_type]

    def best_match(
        self,
        map_type: MapType,
        subject: str,
        *,
        predicate=None,
    ) -> MappingRow | None:
        """Highest-priority row whose token matches `subject`.

        Rows are already ordered, so the first hit is the winner. That is how
        SHAPE SOLVER SPORT beats SHAPE SOLVER and LB PB beats PB without any
        special-casing.
        """
        for row in self._by_type[map_type]:
            if predicate is not None and not predicate(row):
                continue
            if _matches(row, subject):
                return row
        return None


def _matches(row: MappingRow, subject: str) -> bool:
    if row.match_mode is MatchMode.ENDS_WITH:
        return subject.endswith(f" {row.title}") or subject == row.title
    if not contains_token(subject, row.title):
        return False
    if row.match_token_2:
        return contains_token(subject, row.match_token_2)
    return True


def row_from_dict(raw: dict) -> MappingRow:
    """Build a row from a SharePoint list item or a CSV record."""
    title = (raw.get("Title") or "").strip()
    map_type = MapType(raw["MapType"].strip())
    # Sender rows hold an address; everything else holds a match token that
    # must already be in normalized form.
    normalized_title = title if map_type is MapType.SENDER else normalize_token(title)
    priority_raw = (raw.get("Priority") or "").strip()
    return MappingRow(
        title=normalized_title,
        map_type=map_type,
        output_code=(raw.get("OutputCode") or "").strip(),
        folder_name=(raw.get("FolderName") or "").strip(),
        match_mode=MatchMode((raw.get("MatchMode") or "Token").strip() or "Token"),
        match_token_2=normalize_token(raw.get("MatchToken2") or ""),
        priority=int(priority_raw) if priority_raw else 0,
        default_brand=(raw.get("DefaultBrand") or "").strip(),
        default_brand_folder=(raw.get("DefaultBrandFolder") or "").strip(),
        cadence=(raw.get("Cadence") or "Weekly").strip() or "Weekly",
        qlik_only=_flag(raw.get("QlikOnly")),
        active=_flag(raw.get("Active")) if raw.get("Active") is not None else True,
    )


def load_csv(path: str | Path) -> MappingTable:
    with Path(path).open(newline="", encoding="utf-8") as handle:
        return MappingTable(row_from_dict(record) for record in csv.DictReader(handle))
