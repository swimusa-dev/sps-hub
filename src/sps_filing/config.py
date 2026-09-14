"""Runtime configuration, read from app settings."""

from __future__ import annotations

import os
from dataclasses import dataclass


def _require(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"app setting {name} is not set")
    return value


@dataclass(frozen=True)
class Settings:
    mailbox: str
    sharepoint_hostname: str
    sharepoint_site_path: str
    library_name: str
    library_root: str
    mapping_list: str
    lookback_hours: int
    dry_run: bool

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            mailbox=_require("SPS_MAILBOX"),
            sharepoint_hostname=_require("SPS_SP_HOSTNAME"),
            sharepoint_site_path=_require("SPS_SP_SITE_PATH"),
            library_name=os.environ.get("SPS_SP_LIBRARY", "Documents"),
            # Relative to the drive root. Unlike the Power Automate connector,
            # the Graph drive API does not want a "Shared Documents" prefix:
            # the drive *is* the library.
            library_root=os.environ.get(
                "SPS_LIBRARY_ROOT", "/02 - Sales/05 - Published Reports"
            ).rstrip("/"),
            mapping_list=os.environ.get("SPS_MAPPING_LIST", "SPS Filing Map"),
            # Overlap window. Re-examining a few already-filed messages is
            # cheap, and it means an outage self-heals on the next run instead
            # of needing a watermark to be repaired by hand.
            lookback_hours=int(os.environ.get("SPS_LOOKBACK_HOURS", "24")),
            dry_run=os.environ.get("SPS_DRY_RUN", "").lower() in {"1", "true", "yes"},
        )
