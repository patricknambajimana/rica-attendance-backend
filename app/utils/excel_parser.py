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

import html
import io
import re
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


_TD_RE = re.compile(r"<t[dh]\b[^>]*>(.*?)</t[dh]>", re.IGNORECASE | re.DOTALL)
_BR_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")
_TABLE_SPLIT_RE = re.compile(r"<table\b", re.IGNORECASE)


def _decode_html(data: bytes) -> str:
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16", errors="replace")
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("cp1252", errors="replace")


def _cell_text(raw: str) -> str:
    text = _BR_RE.sub(" ", raw)
    text = _TAG_RE.sub("", text)
    text = html.unescape(text).replace("\xa0", " ")
    return re.sub(r"\s+", " ", text).strip()


def _table_cells(block: str) -> list[str]:
    return [_cell_text(c) for c in _TD_RE.findall(block)]


_TD_RE = re.compile(r"<t[dh]\b[^>]*>(.*?)</t[dh]>", re.IGNORECASE | re.DOTALL)
_BR_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")
_TABLE_SPLIT_RE = re.compile(r"<table\b", re.IGNORECASE)


def _decode_html(data: bytes) -> str:
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16", errors="replace")
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("cp1252", errors="replace")


def _cell_text(raw: str) -> str:
    text = _BR_RE.sub(" ", raw)
    text = _TAG_RE.sub("", text)
    text = html.unescape(text).replace("\xa0", " ")
    return re.sub(r"\s+", " ", text).strip()


def _table_cells(block: str) -> list[str]:
    return [_cell_text(c) for c in _TD_RE.findall(block)]


def _parse_html_export(data: bytes) -> pd.DataFrame:
    """
    The device's HTML export is malformed: only the first row of each table
    is wrapped in <tr>, the rest are bare <td> cells. HTML table parsers
    (pandas.read_html, browsers) rebuild rows from <tr>, so they silently
    drop nearly every data row. Instead, read every <td> in document order
    and slice the flat cell list into rows of len(REQUIRED_COLUMNS).
    """
    text = _decode_html(data)
    blocks = _TABLE_SPLIT_RE.split(text)[1:]
    if not blocks:
        raise AppError("Could not read attendance file: no table found", 400)

    ncols = len(REQUIRED_COLUMNS)

    header: list[str] | None = None
    header_block_idx = -1
    leftover: list[str] = []
    for b_idx, block in enumerate(blocks):
        cells = _table_cells(block)
        if "Person ID" not in cells:
            continue
        start = cells.index("Person ID") - 1  # "No." sits just before "Person ID"
        if start < 0 or len(cells) - start < ncols:
            continue
        header = cells[start:start + ncols]
        header_block_idx = b_idx
        leftover = cells[start + ncols:]
        break

    if header is None:
        raise AppError("Could not locate the header row (expected a 'Person ID' column)", 400)

    data_cells: list[str] = []
    if leftover:
        if len(leftover) % ncols == 0:
            data_cells.extend(leftover)

    # Following tables hold the data rows. A table whose cell count isn't a
    # whole number of rows (the footnote / "Date/Time" footer) ends the run.
    for block in blocks[header_block_idx + 1:]:
        cells = _table_cells(block)
        if not cells:
            continue
        if len(cells) % ncols != 0:
            break
        data_cells.extend(cells)

    if not data_cells:
        raise AppError("Header row found but no data rows followed it", 400)

    rows = [data_cells[i:i + ncols] for i in range(0, len(data_cells), ncols)]
    df = pd.DataFrame(rows, columns=header)
    return df.replace({"": None})


def _parse_native_excel(filename: str, data: bytes) -> pd.DataFrame:
    buf = io.BytesIO(data)
    lower = filename.lower()
    try:
        if lower.endswith(".csv"):
            raw = pd.read_csv(buf, header=None, dtype=str)
        elif lower.endswith(".xls"):
            raw = pd.read_excel(buf, header=None, dtype=str, engine="xlrd")
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