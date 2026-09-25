"""
Parses the fingerprint device's daily attendance export into a list of
plain dicts keyed by the 20 raw-data columns from the spec (section 3.1):

    No., Person ID, Name, Department, Position, Gender, Date, Week,
    Timetable, Check-in, Check-out, Work, OT, Attended, Late, Early,
    Absent, Leave, Status, Records

Devices label the export ".xls" but the file is actually an HTML table
(Excel's "Web Page" export format), so it can't be opened with openpyxl
or xlrd. This parser auto-detects that case and falls back to real
.xlsx / .csv for files that have been re-saved in a genuine format.
"""
from __future__ import annotations

import io
from typing import Any

import pandas as pd

from .errors import AppError

REQUIRED_COLUMNS = [
    "No.", "Person ID", "Name", "Department", "Position", "Gender",
    "Date", "Week", "Timetable", "Check-in", "Check-out", "Work", "OT",
    "Attended", "Late", "Early", "Absent", "Leave", "Status", "Records",
]

_INT_COLUMNS = ["Work", "OT", "Attended", "Late", "Early", "Absent", "Leave"]


def parse_attendance_file(filename: str, data: bytes) -> list[dict[str, Any]]:
    """
    Returns one dict per attendance row, with headers normalized to
    REQUIRED_COLUMNS and numeric/date columns coerced to real types.
    Raises AppError (400) on anything that isn't a readable, well-formed
    export.
    """
    if not data:
        raise AppError("Uploaded file is empty", 400)

    if _looks_like_html(data):
        df = _parse_html_export(data)
    else:
        df = _parse_native_excel(filename, data)

    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise AppError(f"Missing required column(s): {', '.join(missing)}", 400)

    df = df[REQUIRED_COLUMNS].copy()

    # Drop fully-blank rows (trailing spacer rows are common in these exports)
    df = df[~df.drop(columns=["No."]).isna().all(axis=1)]
    df = df[df["Person ID"].notna() & (df["Person ID"].astype(str).str.strip() != "")]

    if df.empty:
        raise AppError("No data rows found in the file", 400)

    df["Person ID"] = df["Person ID"].astype(str).str.strip()
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    if df["Date"].isna().any():
        raise AppError("One or more rows have an unreadable Date value", 400)

    for col in _INT_COLUMNS:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)

    df["No."] = pd.to_numeric(df["No."], errors="coerce").astype("Int64")

    for col in ["Name", "Department", "Position", "Gender", "Week", "Timetable",
                "Check-in", "Check-out", "Status", "Records"]:
        df[col] = df[col].astype(str).str.strip().replace({"nan": None, "None": None})

    return df.to_dict(orient="records")


def _looks_like_html(data: bytes) -> bool:
    head = data[:512].lstrip().lower()
    return head.startswith(b"<html") or head.startswith(b"<!doctype") or b"<table" in head


def _parse_html_export(data: bytes) -> pd.DataFrame:
    try:
        tables = pd.read_html(io.BytesIO(data))
    except ValueError as exc:
        raise AppError(f"Could not read attendance file: {exc}", 400) from exc

    header_row: list[Any] | None = None
    header_table_idx: int | None = None
    header_row_idx: int | None = None

    for t_idx, table in enumerate(tables):
        for r_idx, row in table.iterrows():
            values = [str(v).strip() for v in row.tolist()]
            if "Person ID" in values:
                header_row = values
                header_table_idx = t_idx
                header_row_idx = r_idx
                break
        if header_row is not None:
            break

    if header_row is None:
        raise AppError("Could not locate the header row (expected a 'Person ID' column)", 400)

    ncols = len(header_row)
    frames = []

    # any data rows sitting below the header inside its own table
    below = tables[header_table_idx].iloc[header_row_idx + 1:]
    if not below.empty:
        below = below.copy()
        below.columns = header_row
        frames.append(below)

    # subsequent tables with the same column count are more data rows;
    # a table with a different column count (e.g. the footnote table) ends the run
    for t_idx in range(header_table_idx + 1, len(tables)):
        table = tables[t_idx]
        if table.shape[1] != ncols:
            break
        table = table.copy()
        table.columns = header_row
        frames.append(table)

    if not frames:
        raise AppError("Header row found but no data rows followed it", 400)

    return pd.concat(frames, ignore_index=True)


def _parse_native_excel(filename: str, data: bytes) -> pd.DataFrame:
    buf = io.BytesIO(data)
    lower = filename.lower()
    try:
        if lower.endswith(".csv"):
            raw = pd.read_csv(buf, header=None, dtype=str)
        else:
            raw = pd.read_excel(buf, header=None, dtype=str, engine="openpyxl")
    except Exception as exc:  # noqa: BLE001 - surface as a clean 400
        raise AppError(f"Could not read attendance file: {exc}", 400) from exc

    header_row_idx = None
    for idx, row in raw.iterrows():
        if "Person ID" in [str(v).strip() for v in row.tolist()]:
            header_row_idx = idx
            break

    if header_row_idx is None:
        raise AppError("Could not locate the header row (expected a 'Person ID' column)", 400)

    df = raw.iloc[header_row_idx + 1:].copy()
    df.columns = [str(v).strip() for v in raw.iloc[header_row_idx].tolist()]
    return df