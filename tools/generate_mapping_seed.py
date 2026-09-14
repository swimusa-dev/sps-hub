"""Regenerate data/sps_filing_map_seed.csv.

The CSV is both the import file for the SharePoint `SPS Filing Map` list and
the fixture the parser tests run against. Generating it keeps priorities
consistent with the tokens: for retailers and brands, priority is the token's
character count, so longest-first ordering cannot drift when someone adds a row
by hand later.

Report-family priorities are explicit and deliberately not length-based.
"""

from __future__ import annotations

import csv
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from sps_filing.normalize import normalize_token  # noqa: E402

FIELDS = [
    "Title", "MapType", "MatchMode", "MatchToken2", "Priority", "OutputCode",
    "FolderName", "DefaultBrand", "DefaultBrandFolder", "Cadence", "QlikOnly", "Active",
]

SENDERS = [
    ("analytics@spscommerce.com", "REPORT"),
    ("POSServices@spscommerce.com", "ADMIN"),
    ("no-reply@spscommerce.com", "ADMIN"),
    ("retailintelligence@spscommerce.com", "ADMIN"),
]

CROSS_RETAILER = ["ALL RETAILERS", "TOP 6 ACCTS"]

RETAILERS = [
    ("BLOOMINGDALES", "BLOOMINGDALES", "Bloomingdales"),
    ("JCPINTERNET", "JCPINTERNET", "JCP Internet"),
    ("NORDSTROM", "NORDSTROM", "Nordstrom"),
    ("JCPENNEY", "JCPENNEY", "JCPenney"),
    ("VON MAUR", "VON-MAUR", "Von Maur"),
    ("DILLARDS", "DILLARDS", "Dillards"),
    ("ACADEMY", "ACADEMY", "Academy"),
    ("NEIMANS", "NEIMANS", "Neimans"),
    ("BEALLS", "BEALLS", "Bealls"),
    ("MACYS", "MACYS", "Macys"),
    ("MAYCS", "MACYS", "Macys"),          # live SPS typo, aliased not ignored
    ("KOHLS", "KOHLS", "Kohls"),
    ("BELK", "BELK", "Belk"),
    ("SAKS", "SAKS", "Saks"),
    ("JCP", "JCPENNEY", "JCPenney"),
    ("EBW", "EBW", "EBW"),
    ("HBC", "EBW", "EBW"),                # HBC was repurposed as EBW
]

FAMILIES = [
    ("QLIK SELL THRU", "", 180, "QLIK-SELL-THRU", "06 Qlik Sell Thru", "ALL-BRANDS", "All Brands"),
    ("SPS RETURNS REPORT", "", 170, "RETURNS", "07 Returns", "ALL-BRANDS", "All Brands"),
    ("ALL DIVISIONS", "", 160, "ROLLUP", "08 Division Rollups", "ALL-DIVISIONS", "All Divisions"),
    ("ALL BRANDS TOTAL", "", 160, "ROLLUP", "08 Division Rollups", "ALL-BRANDS", "All Brands"),
    ("TOP 6 ACCTS", "", 160, "ROLLUP", "08 Division Rollups", "ALL-BRANDS", "All Brands"),
    ("BY DOOR & STYLE PERFORMANCE", "", 150, "DOOR-AND-STYLE", "05 Door and Style", "", ""),
    ("DOOR PERFORMANCE", "", 140, "DOOR-PERFORMANCE", "04 Door Performance", "", ""),
    ("STYLE SELLING", "", 130, "STYLE-SELLING", "01 Style Selling", "", ""),
    ("WEEKLY TREND ANALYSIS", "", 120, "WEEKLY-TREND", "02 Weekly Trend", "", ""),
    ("WTD", "STD", 110, "PERIOD-TO-DATE", "03 Period To-Date", "", ""),
]

BRANDS = [
    ("SHAPE SOLVER SPORT", "SHAPE-SOLVER-SPORT", "Shape Solver Sport"),
    ("ALL BRANDS TOTAL", "ALL-BRANDS", "All Brands"),
    ("AMERICAN BEACH", "AMERICAN-BEACH", "American Beach"),
    ("MIMI SIGNATURE", "MIMI-SIGNATURE", "Mimi Signature"),
    ("SWIM SOLUTIONS", "SWIM-SOLUTIONS", "Swim Solutions"),
    ("CONTROL BRANDS", "CONTROL-BRANDS", "Control Brands"),
    ("ORAGEOUS KIDS", "ORAGEOUS-KIDS", "Orageous Kids"),
    ("GREAT LENGTHS", "GREAT-LENGTHS", "Great Lengths"),
    ("ALL DIVISIONS", "ALL-DIVISIONS", "All Divisions"),
    ("ORAGEOUS JRS", "ORAGEOUS-JRS", "Orageous Jrs"),
    ("SHAPE SOLVER", "SHAPE-SOLVER", "Shape Solver"),
    ("STEVE MADDEN", "STEVE-MADDEN", "Steve Madden"),
    ("LAUREN MISSY", "LAUREN-MISSY", "Lauren Missy"),
    ("LAUREN WOMAN", "LAUREN-WOMAN", "Lauren Woman"),
    ("SALT & COVE", "SALT-AND-COVE", "Salt and Cove"),
    ("BAL HARBOUR", "BAL-HARBOUR", "Bal Harbour"),
    ("MIRACLESUIT", "MIRACLESUIT", "Miraclesuit"),
    ("ALL BRANDS", "ALL-BRANDS", "All Brands"),
    ("ECO BEACH", "ECO-BEACH", "Eco Beach"),
    ("VITAMIN A", "VITAMIN-A", "Vitamin A"),
    ("LONGITUDE", "LONGITUDE", "Longitude"),
    ("FREELY", "FREELY", "Freely"),
    ("LAUREN", "LAUREN", "Lauren"),
    ("POLO", "POLO", "Polo"),
    ("GLKO", "GLKO", "GLKO"),
    ("JRS", "JRS", "Jrs"),
    ("S3", "S3", "S3"),
    ("TS", "TS", "TS"),
]

# Brand codes that appear only in Qlik subjects. LB PB must outrank PB, which
# the length-based priority handles.
QLIK_BRANDS = ["LB PB", "RL", "MG", "MS", "VA", "SS", "BF", "PB"]

CALENDARS = [
    ("4-5-4 Calendar", "Token", 200, "454"),
    ("Supplier (FISCAL) Calendar", "Token", 200, "SUPPLIER"),
    ("SUPPLIER", "EndsWith", 100, "SUPPLIER"),
    ("NRF", "EndsWith", 100, "NRF"),
]


def build_rows() -> list[dict]:
    rows: list[dict] = []

    def add(**kw):
        row = {f: "" for f in FIELDS}
        row.update(Cadence="", QlikOnly="No", Active="Yes")
        row.update(kw)
        rows.append(row)

    for address, code in SENDERS:
        add(Title=address, MapType="Sender", MatchMode="Token", Priority=100, OutputCode=code)

    for token in CROSS_RETAILER:
        add(Title=normalize_token(token), MapType="Retailer", MatchMode="Token",
            Priority=900, OutputCode="CROSS-RETAILER", FolderName="_Cross-Retailer")

    for token, code, folder in RETAILERS:
        title = normalize_token(token)
        add(Title=title, MapType="Retailer", MatchMode="Token", Priority=len(title),
            OutputCode=code, FolderName=folder)

    for token, token2, priority, code, folder, dbrand, dfolder in FAMILIES:
        add(Title=normalize_token(token), MapType="ReportFamily", MatchMode="Token",
            MatchToken2=normalize_token(token2), Priority=priority, OutputCode=code,
            FolderName=folder, DefaultBrand=dbrand, DefaultBrandFolder=dfolder,
            Cadence="Weekly")

    for token, code, folder in BRANDS:
        title = normalize_token(token)
        add(Title=title, MapType="Brand", MatchMode="Token", Priority=len(title),
            OutputCode=code, FolderName=folder)

    for token in QLIK_BRANDS:
        title = normalize_token(token)
        add(Title=title, MapType="Brand", MatchMode="Token", Priority=len(title),
            OutputCode=title.replace(" ", "-"), FolderName=title, QlikOnly="Yes")

    for token, mode, priority, code in CALENDARS:
        add(Title=normalize_token(token), MapType="Calendar", MatchMode=mode,
            Priority=priority, OutputCode=code)

    return rows


def main() -> None:
    target = Path(__file__).resolve().parents[1] / "data" / "sps_filing_map_seed.csv"
    rows = build_rows()
    with target.open("w", newline="", encoding="utf-8") as handle:
        # Force LF so regenerating is a no-op in git and the CI
        # drift check compares content rather than line endings.
        writer = csv.DictWriter(handle, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {len(rows)} rows to {target}")
    for map_type, count in sorted(Counter(r["MapType"] for r in rows).items()):
        print(f"  {map_type:<13} {count}")


if __name__ == "__main__":
    main()
