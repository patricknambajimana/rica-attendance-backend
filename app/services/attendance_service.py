"""
Spec sections 3.3 (steps 2-5) and 5.1-5.3:
upload -> raw database -> anomaly checker -> HR verify/edit -> attendance_final.
"""
from __future__ import annotations

from io import BytesIO
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill

from ..extensions import db
from ..schemas.attendance import AttendanceEditIn
from ..utils.audit import date_only, log_action, utcnow
from ..utils.dates import date_range_filter
from ..utils.errors import AppError
from ..utils.excel_parser import parse_attendance_file
from ..utils.scope import scoped_department_id
from ..utils.validators import role_str

ALLOWED_EXTENSIONS = (".xls", ".xlsx", ".csv")

# Status codes used by the device export:
# W = attended, A = absent, LV = leave/business trip, # = weekend
ATTENDED_STATUSES = {"W", "L", "E", "OT1", "OT2", "OT3"}
ABSENT_STATUSES = {"A"}
EXEMPT_STATUSES = {"LV", "#"}
LEAVE_STATUS = "LV"

_RAW_EDIT_FIELDS = {
    "check_in": "checkIn",
    "check_out": "checkOut",
    "work_min": "workMin",
    "ot_min": "otMin",
    "attended_min": "attendedMin",
    "late_min": "lateMin",
    "early_min": "earlyMin",
    "absent_min": "absentMin",
    "leave_min": "leaveMin",
    "status": "status",
    "notes": "notes",
}

_EMPLOYEE_INCLUDE = {"employee": {"include": {"department": True}}}


# ============================================================
# IMPORT
# ============================================================

def import_attendance_file(
    filename: str, data: bytes, uploaded_by_id: str
) -> dict[str, Any]:
    if not filename or not filename.lower().endswith(ALLOWED_EXTENSIONS):
        raise AppError(
            f"Unsupported file type. Allowed: {', '.join(ALLOWED_EXTENSIONS)}", 400
        )

    rows = parse_attendance_file(filename, data)
    employee_ids = _upsert_employees_and_departments(rows)

    batch = db.attendancebatch.create(
        data={
            "filename": filename,
            "uploadedById": uploaded_by_id,
            "rowCount": len(rows),
        }
    )

    raw_payload, in_file_duplicates = _dedupe_payload(
        [_to_raw_record(row, employee_ids[row["Person ID"]], batch.id) for row in rows]
    )

    existing = _existing_raw_by_key(raw_payload)
    to_create, to_refresh, skipped_verified = _plan_import(raw_payload, existing)

    created_count = 0
    if to_create:
        create_result = db.attendanceraw.create_many(
            data=to_create, skip_duplicates=True
        )
        created_count = (
            create_result if isinstance(create_result, int) else create_result.count
        )

    refreshed_ids: list[str] = []
    for existing_id, payload in to_refresh:
        db.attendanceraw.update(where={"id": existing_id}, data=payload)
        refreshed_ids.append(existing_id)

    if refreshed_ids:
        db.anomaly.delete_many(
            where={"attendanceRawId": {"in": refreshed_ids}, "resolved": False}
        )

    inserted_count = created_count + len(refreshed_ids)
    duplicate_count = in_file_duplicates + skipped_verified

    inserted_rows = db.attendanceraw.find_many(where={"batchId": batch.id})
    anomaly_payload = detect_anomalies(inserted_rows, batch.id)
    if anomaly_payload:
        db.anomaly.create_many(data=anomaly_payload)

    batch = db.attendancebatch.update(
        where={"id": batch.id},
        data={
            "insertedCount": inserted_count,
            "duplicateCount": duplicate_count,
            "anomalyCount": len(anomaly_payload),
        },
    )

    log_action(
        "UPLOAD",
        user_id=uploaded_by_id,
        entity_type="AttendanceBatch",
        entity_id=batch.id,
        delta={
            "filename": filename,
            "rowCount": batch.rowCount,
            "insertedCount": batch.insertedCount,
            "duplicateCount": batch.duplicateCount,
            "anomalyCount": batch.anomalyCount,
        },
    )

    return {
        "batchId": batch.id,
        "filename": batch.filename,
        "rowCount": batch.rowCount,
        "insertedCount": batch.insertedCount,
        "createdCount": created_count,
        "refreshedCount": len(refreshed_ids),
        "duplicateCount": batch.duplicateCount,
        "anomalyCount": batch.anomalyCount,
    }


# ============================================================
# BATCHES
# ============================================================

def list_batches(limit: int = 50):
    return db.attendancebatch.find_many(order={"createdAt": "desc"}, take=limit)


def delete_batch(batch_id: str, user) -> dict[str, Any]:
    """
    Permanently delete an upload batch and every record that came from it —
    raw rows, their promoted attendance_final rows, and their anomalies —
    regardless of age or verification status. ADMIN only; there is no
    "too old" or "already verified" exception, by design: an admin can
    always undo a bad upload.

    This is destructive and not reversible. If the raw rows have already
    been verified/edited by HR, that corrected data is deleted too.
    """
    batch = db.attendancebatch.find_first(where={"id": batch_id})
    if batch is None:
        raise AppError("Batch not found", 404)

    raw_rows = db.attendanceraw.find_many(where={"batchId": batch_id})
    raw_ids = [r.id for r in raw_rows]

    final_deleted = 0
    anomaly_deleted = 0
    if raw_ids:
        # attendance_final rows reference attendance_raw by FK, so they must
        # go first or the raw delete below would hit a foreign-key error.
        final_result = db.attendancefinal.delete_many(where={"attendanceRawId": {"in": raw_ids}})
        final_deleted = final_result if isinstance(final_result, int) else final_result.count

    anomaly_result = db.anomaly.delete_many(where={"batchId": batch_id})
    anomaly_deleted = anomaly_result if isinstance(anomaly_result, int) else anomaly_result.count

    raw_result = db.attendanceraw.delete_many(where={"batchId": batch_id})
    raw_deleted = raw_result if isinstance(raw_result, int) else raw_result.count

    db.attendancebatch.delete(where={"id": batch_id})

    summary = {
        "batchId": batch_id,
        "filename": batch.filename,
        "rawDeleted": raw_deleted,
        "finalDeleted": final_deleted,
        "anomalyDeleted": anomaly_deleted,
    }

    log_action(
        "DELETE_BATCH",
        user_id=user.id,
        entity_type="AttendanceBatch",
        entity_id=batch_id,
        delta=summary,
    )
    return summary


#GET DAILY ATTENDANCE TABLE 

def get_daily_attendance_table(
    user,
    *,
    batch_id: str | None = None,
    department_id: str | None = None,
    office: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    status: str | None = None,
    unverified_only: bool = False,
    search: str | None = None,
    take: int = 5000,
    skip: int = 0,
) -> dict[str, Any]:
    """
    Return all employees' daily attendance in table-ready format
    with column headers matching the original Excel columns.
    """
    take = min(max(int(take or 5000), 1), 100_000)
    skip = max(int(skip or 0), 0)

    # ── Build filter ──
    where = _build_raw_where(
        user,
        batch_id=batch_id,
        department_id=department_id,
        office=office,
        date_from=date_from,
        date_to=date_to,
        status=status,
        unverified_only=unverified_only,
    )

    # ── Search by name or Person ID (merged into the existing employee filter,
    # not replacing it — otherwise an HOD's department scope would be wiped
    # out whenever `search` is also passed) ──
    if search:
        search = search.strip()
        employee_filter = dict((where.get("employee") or {}).get("is") or {})
        employee_filter["OR"] = [
            {"fullName": {"contains": search, "mode": "insensitive"}},
            {"personId": {"contains": search, "mode": "insensitive"}},
        ]
        where["employee"] = {"is": employee_filter}

    total = db.attendanceraw.count(where=where)

    records = db.attendanceraw.find_many(
        where=where,
        include=_EMPLOYEE_INCLUDE,
        order={"date": "asc"},
        take=take,
        skip=skip,
    )

    # ── Column headers (match Excel exactly) ──
    columns = [
        {"key": "row_no",       "label": "No.",        "type": "number"},
        {"key": "person_id",    "label": "Person ID",  "type": "text"},
        {"key": "name",         "label": "Name",       "type": "text"},
        {"key": "department",   "label": "Department", "type": "text"},
        {"key": "position",     "label": "Position",   "type": "text"},
        {"key": "gender",       "label": "Gender",     "type": "text"},
        {"key": "date",         "label": "Date",       "type": "date"},
        {"key": "week",         "label": "Week",       "type": "text"},
        {"key": "timetable",    "label": "Timetable",  "type": "text"},
        {"key": "check_in",     "label": "Check-in",   "type": "time"},
        {"key": "check_out",    "label": "Check-out",  "type": "time"},
        {"key": "work_min",     "label": "Work",       "type": "number"},
        {"key": "ot_min",       "label": "OT",         "type": "number"},
        {"key": "attended_min", "label": "Attended",   "type": "number"},
        {"key": "late_min",     "label": "Late",       "type": "number"},
        {"key": "early_min",    "label": "Early",      "type": "number"},
        {"key": "absent_min",   "label": "Absent",     "type": "number"},
        {"key": "leave_min",    "label": "Leave",      "type": "number"},
        {"key": "status",       "label": "Status",     "type": "badge"},
        {"key": "records",      "label": "Records",    "type": "text"},
    ]

    # ── Map records to rows ──
    rows = [serialize_raw(r) for r in records]

    # ── Summary counts ──
    summary = _build_attendance_summary(records)

    page = (skip // take) + 1 if take else 1
    total_pages = (total + take - 1) // take if take else 1

    return {
        "columns": columns,
        "rows": rows,
        "summary": summary,
        "pagination": {
            "total": total,
            "returned": len(rows),
            "page": page,
            "page_size": take,
            "total_pages": total_pages,
            "has_next": page < total_pages,
            "has_prev": page > 1,
        },
    }


def _build_attendance_summary(records: list) -> dict[str, Any]:
    """Aggregate counts per status for the current page of records."""
    status_counts: dict[str, int] = {}
    total_work = 0
    total_ot = 0
    total_attended = 0
    total_late = 0
    total_early = 0
    total_absent = 0
    total_leave = 0

    for r in records:
        status = (r.status or "-").strip().upper()
        status_counts[status] = status_counts.get(status, 0) + 1
        total_work += r.workMin or 0
        total_ot += r.otMin or 0
        total_attended += r.attendedMin or 0
        total_late += r.lateMin or 0
        total_early += r.earlyMin or 0
        total_absent += r.absentMin or 0
        total_leave += r.leaveMin or 0

    return {
        "total_rows": len(records),
        "status_breakdown": status_counts,
        "totals": {
            "work_min": total_work,
            "ot_min": total_ot,
            "attended_min": total_attended,
            "late_min": total_late,
            "early_min": total_early,
            "absent_min": total_absent,
            "leave_min": total_leave,
        },
    }
# ============================================================
# RAW RECORDS
# ============================================================
# list_raw_records / list_raw_records_paginated were removed: GET /raw was
# a redundant list endpoint — everything it did (batch/department/office/
# date/status/unverified filters, pagination, an "all" full-export mode) is
# now covered by GET /daily. _build_raw_where stays: it's still shared by
# /daily, /export, and the KPI-style aggregates below.

def _build_raw_where(
    user,
    *,
    batch_id: str | None = None,
    department_id: str | None = None,
    office: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    status: str | None = None,
    unverified_only: bool = False,
) -> dict[str, Any]:
    """Build the `where` filter shared by list + count."""
    dept_id = scoped_department_id(user, department_id)
    where: dict[str, Any] = {}

    if batch_id:
        where["batchId"] = batch_id
    if status:
        where["status"] = status
    if unverified_only:
        where["verifiedAt"] = None

    date_filt = date_range_filter(date_from, date_to)
    if date_filt:
        where["date"] = date_filt

    employee_filter: dict[str, Any] = {}
    if dept_id:
        employee_filter["departmentId"] = dept_id
    if office:
        employee_filter["department"] = {"is": {"office": office}}
    if employee_filter:
        where["employee"] = {"is": employee_filter}

    return where


def get_raw_record(raw_id: str, user):
    record = db.attendanceraw.find_unique(
        where={"id": raw_id}, include=_EMPLOYEE_INCLUDE
    )
    if record is None:
        raise AppError("Attendance record not found", 404)
    _assert_can_view_employee(user, record.employee)
    return record


# ============================================================
# EDIT + VERIFY
# ============================================================

def edit_and_verify(raw_id: str, user, body: AttendanceEditIn):
    record = get_raw_record(raw_id, user)
    before = _snapshot(record)
    data: dict[str, Any] = {}
    sent = body.model_fields_set

    for api_name, prisma_name in _RAW_EDIT_FIELDS.items():
        if api_name in sent:
            data[prisma_name] = getattr(body, api_name)

    if body.promote_to_final:
        data["verifiedAt"] = utcnow()
        data["verifiedById"] = user.id

    updated = db.attendanceraw.update(
        where={"id": raw_id},
        data=data,
        include=_EMPLOYEE_INCLUDE,
    )

    if body.resolve_anomalies:
        db.anomaly.update_many(
            where={"attendanceRawId": raw_id, "resolved": False},
            data={
                "resolved": True,
                "resolvedById": user.id,
                "resolvedAt": utcnow(),
            },
        )

    if body.promote_to_final:
        _upsert_final(updated, user.id)

    log_action(
        "EDIT_ATTENDANCE",
        user_id=user.id,
        entity_type="AttendanceRaw",
        entity_id=raw_id,
        delta={"before": before, "after": _snapshot(updated)},
    )
    return updated


# ============================================================
# ANOMALIES
# ============================================================

def resolve_anomaly(anomaly_id: str, user, note: str | None = None):
    anomaly = db.anomaly.find_unique(where={"id": anomaly_id})
    if anomaly is None:
        raise AppError("Anomaly not found", 404)
    if anomaly.resolved:
        return anomaly

    updated = db.anomaly.update(
        where={"id": anomaly_id},
        data={
            "resolved": True,
            "resolvedById": user.id,
            "resolvedAt": utcnow(),
        },
    )
    if note:
        raw = db.attendanceraw.find_unique(where={"id": anomaly.attendanceRawId})
        if raw:
            merged = f"{raw.notes}\n{note}".strip() if raw.notes else note
            db.attendanceraw.update(where={"id": raw.id}, data={"notes": merged})

    log_action(
        "RESOLVE_ANOMALY",
        user_id=user.id,
        entity_type="Anomaly",
        entity_id=anomaly_id,
        delta={"note": note, "type": str(anomaly.type)},
    )
    return updated


def list_anomalies(
    user,
    *,
    batch_id: str | None = None,
    resolved: bool | None = False,
    take: int = 200,
):
    where: dict[str, Any] = {}
    if batch_id:
        where["batchId"] = batch_id
    if resolved is False:
        where["resolved"] = False
    elif resolved is True:
        where["resolved"] = True

    dept_id = scoped_department_id(user)
    if dept_id:
        where["attendanceRaw"] = {
            "is": {"employee": {"is": {"departmentId": dept_id}}}
        }

    return db.anomaly.find_many(
        where=where,
        include={"attendanceRaw": {"include": _EMPLOYEE_INCLUDE}},
        order={"createdAt": "asc"},
        take=min(take, 500),
    )


# ============================================================
# FINAL RECORDS — with pagination
# ============================================================

def list_final_records(user, **filters):
    """Original list function — kept for backward compatibility."""
    return list_final_records_paginated(user, **filters)["records"]


def _build_final_where(user, **filters) -> dict[str, Any]:
    dept_id = scoped_department_id(user, filters.get("department_id"))
    where: dict[str, Any] = {}

    date_filt = date_range_filter(filters.get("date_from"), filters.get("date_to"))
    if date_filt:
        where["date"] = date_filt

    employee_filter: dict[str, Any] = {}
    if dept_id:
        employee_filter["departmentId"] = dept_id
    if filters.get("office"):
        employee_filter["department"] = {"is": {"office": filters["office"]}}
    if employee_filter:
        where["employee"] = {"is": employee_filter}

    return where


def list_final_records_paginated(user, **filters) -> dict[str, Any]:
    """
    Return paginated final records plus pagination metadata.
    """
    take = min(max(int(filters.get("take") or 200), 1), 500)
    skip = max(int(filters.get("skip") or 0), 0)

    where = _build_final_where(user, **filters)

    total = db.attendancefinal.count(where=where)

    records = db.attendancefinal.find_many(
        where=where,
        include=_EMPLOYEE_INCLUDE,
        order={"date": "asc"},
        take=take,
        skip=skip,
    )

    page = (skip // take) + 1 if take else 1
    total_pages = (total + take - 1) // take if take else 1

    return {
        "records": records,
        "total": total,
        "page": page,
        "page_size": take,
        "total_pages": total_pages,
    }


# ============================================================
# ANOMALY DETECTION
# ============================================================

def detect_anomalies(raw_rows: list, batch_id: str) -> list[dict[str, Any]]:
    anomalies: list[dict[str, Any]] = []

    for r in raw_rows:
        status = (r.status or "").upper()

        for label, value in (
            ("Work", r.workMin),
            ("OT", r.otMin),
            ("Attended", r.attendedMin),
            ("Late", r.lateMin),
            ("Early", r.earlyMin),
            ("Absent", r.absentMin),
            ("Leave", r.leaveMin),
        ):
            if value < 0:
                anomalies.append(
                    _anomaly(
                        batch_id,
                        r.id,
                        "NEGATIVE_VALUE",
                        f"{label} minutes is negative ({value})",
                    )
                )

        no_checkin = not r.checkIn or r.checkIn == "-"
        no_checkout = not r.checkOut or r.checkOut == "-"
        if (
            status not in EXEMPT_STATUSES
            and status not in ABSENT_STATUSES
            and (no_checkin or no_checkout)
        ):
            anomalies.append(
                _anomaly(
                    batch_id,
                    r.id,
                    "MISSING_PUNCH",
                    "Missing check-in or check-out for a non-absent, non-leave day",
                )
            )

        if status in ATTENDED_STATUSES and r.attendedMin == 0:
            anomalies.append(
                _anomaly(
                    batch_id,
                    r.id,
                    "STATUS_MISMATCH",
                    f"Status is '{r.status}' but attended minutes is 0",
                )
            )
        if status in ABSENT_STATUSES and r.attendedMin > 0:
            anomalies.append(
                _anomaly(
                    batch_id,
                    r.id,
                    "STATUS_MISMATCH",
                    f"Status is 'A' (Absent) but attended minutes is {r.attendedMin}",
                )
            )

        if status in ABSENT_STATUSES and r.absentMin <= 0:
            anomalies.append(
                _anomaly(
                    batch_id,
                    r.id,
                    "ABSENT_INCONSISTENCY",
                    "Status is 'A' (Absent) but absent minutes is 0",
                )
            )
        if (
            status not in ABSENT_STATUSES
            and status not in EXEMPT_STATUSES
            and r.absentMin > 0
        ):
            anomalies.append(
                _anomaly(
                    batch_id,
                    r.id,
                    "ABSENT_INCONSISTENCY",
                    f"Status is '{r.status}' but absent minutes is {r.absentMin}",
                )
            )

    return anomalies


# ============================================================
# LEAVE
# ============================================================

def apply_leave_to_days(
    employee_id: str,
    dates: list,
    user_id: str,
    leave_type: str,
    reason: str | None,
) -> int:
    """Mark each date as LV on raw (if present) and upsert attendance_final."""
    updated = 0
    note = f"Leave ({leave_type})" + (f": {reason}" if reason else "")
    for day in dates:
        raw = db.attendanceraw.find_first(
            where={"employeeId": employee_id, "date": day}
        )
        payload = {
            "status": LEAVE_STATUS,
            "leaveMin": 480,
            "attendedMin": 0,
            "lateMin": 0,
            "earlyMin": 0,
            "absentMin": 0,
            "workMin": 0,
            "checkIn": None,
            "checkOut": None,
            "notes": note,
            "verifiedAt": utcnow(),
            "verifiedById": user_id,
        }
        if raw:
            updated_raw = db.attendanceraw.update(
                where={"id": raw.id}, data=payload
            )
            db.anomaly.update_many(
                where={"attendanceRawId": raw.id, "resolved": False},
                data={
                    "resolved": True,
                    "resolvedById": user_id,
                    "resolvedAt": utcnow(),
                },
            )
            _upsert_final(updated_raw, user_id)
            updated += 1
        else:
            db.attendancefinal.upsert(
                where={"employeeId_date": {"employeeId": employee_id, "date": day}},
                data={
                    "create": {
                        "employeeId": employee_id,
                        "date": day,
                        "status": LEAVE_STATUS,
                        "leaveMin": 480,
                        "notes": note,
                        "verifiedById": user_id,
                    },
                    "update": {
                        "status": LEAVE_STATUS,
                        "leaveMin": 480,
                        "attendedMin": 0,
                        "lateMin": 0,
                        "earlyMin": 0,
                        "absentMin": 0,
                        "workMin": 0,
                        "checkIn": None,
                        "checkOut": None,
                        "notes": note,
                        "verifiedById": user_id,
                        "verifiedAt": utcnow(),
                    },
                },
            )
            updated += 1
    return updated


# ============================================================
# SERIALIZATION
# ============================================================

def serialize_raw(record) -> dict[str, Any]:
    emp = getattr(record, "employee", None)
    dept = getattr(emp, "department", None) if emp else None
    return {
        "id": record.id,
        "batch_id": getattr(record, "batchId", None),
        "row_no": record.rowNo,
        "date": record.date.date().isoformat() if record.date else None,
        "week": record.week,
        "timetable": record.timetable,
        "check_in": record.checkIn,
        "check_out": record.checkOut,
        "work_min": record.workMin,
        "ot_min": record.otMin,
        "attended_min": record.attendedMin,
        "late_min": record.lateMin,
        "early_min": record.earlyMin,
        "absent_min": record.absentMin,
        "leave_min": record.leaveMin,
        "status": record.status,
        "records": getattr(record, "records", None),
        "notes": getattr(record, "notes", None),
        "verified_at": (
            record.verifiedAt.isoformat()
            if getattr(record, "verifiedAt", None)
            else None
        ),
        "person_id": emp.personId if emp else None,
        "name": emp.fullName if emp else None,
        "department": dept.name if dept else None,
        "office": dept.office if dept else None,
        "position": emp.position if emp else None,
        "gender": emp.gender if emp else None,
        "employee_id": record.employeeId,
    }


def serialize_anomaly(a) -> dict[str, Any]:
    raw = getattr(a, "attendanceRaw", None)
    return {
        "id": a.id,
        "batch_id": a.batchId,
        "attendance_raw_id": a.attendanceRawId,
        "type": str(getattr(a.type, "value", a.type)),
        "message": a.message,
        "resolved": a.resolved,
        "resolved_by_id": a.resolvedById,
        "resolved_at": a.resolvedAt.isoformat() if a.resolvedAt else None,
        "created_at": a.createdAt.isoformat() if a.createdAt else None,
        "record": serialize_raw(raw) if raw else None,
    }


# ============================================================
# EXPORT TO EXCEL (NEW)
# ============================================================

def export_to_excel(
    user,
    *,
    batch_id: str | None = None,
    department_id: str | None = None,
    office: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    status: str | None = None,
) -> BytesIO:
    """
    Export filtered attendance raw records to Excel.
    Returns a BytesIO buffer suitable for Flask's send_file.
    """
    where = _build_raw_where(
        user,
        batch_id=batch_id,
        department_id=department_id,
        office=office,
        date_from=date_from,
        date_to=date_to,
        status=status,
    )

    records = db.attendanceraw.find_many(
        where=where,
        include=_EMPLOYEE_INCLUDE,
        order={"date": "asc"},
        take=10000,
    )

    wb = Workbook()
    ws = wb.active
    ws.title = "Attendance"

    headers = [
        "No.", "Person ID", "Name", "Department", "Position", "Gender",
        "Date", "Week", "Timetable", "Check-in", "Check-out",
        "Work (min)", "OT (min)", "Attended (min)",
        "Late (min)", "Early (min)", "Absent (min)", "Leave (min)",
        "Status", "Notes", "Verified",
    ]

    header_fill = PatternFill(
        start_color="1d6f5f", end_color="1d6f5f", fill_type="solid"
    )
    header_font = Font(bold=True, color="FFFFFF")

    for col, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center", vertical="center")

    for idx, r in enumerate(records, start=2):
        emp = getattr(r, "employee", None)
        dept = getattr(emp, "department", None) if emp else None

        ws.cell(row=idx, column=1, value=r.rowNo)
        ws.cell(row=idx, column=2, value=emp.personId if emp else None)
        ws.cell(row=idx, column=3, value=emp.fullName if emp else None)
        ws.cell(row=idx, column=4, value=dept.name if dept else None)
        ws.cell(row=idx, column=5, value=emp.position if emp else None)
        ws.cell(row=idx, column=6, value=emp.gender if emp else None)
        ws.cell(
            row=idx,
            column=7,
            value=r.date.strftime("%Y-%m-%d") if r.date else None,
        )
        ws.cell(row=idx, column=8, value=r.week)
        ws.cell(row=idx, column=9, value=r.timetable)
        ws.cell(row=idx, column=10, value=r.checkIn)
        ws.cell(row=idx, column=11, value=r.checkOut)
        ws.cell(row=idx, column=12, value=r.workMin)
        ws.cell(row=idx, column=13, value=r.otMin)
        ws.cell(row=idx, column=14, value=r.attendedMin)
        ws.cell(row=idx, column=15, value=r.lateMin)
        ws.cell(row=idx, column=16, value=r.earlyMin)
        ws.cell(row=idx, column=17, value=r.absentMin)
        ws.cell(row=idx, column=18, value=r.leaveMin)
        ws.cell(row=idx, column=19, value=r.status)
        ws.cell(row=idx, column=20, value=getattr(r, "notes", None))
        ws.cell(
            row=idx,
            column=21,
            value="Yes" if getattr(r, "verifiedAt", None) else "No",
        )

    # Auto-size columns
    for col in ws.columns:
        max_len = 0
        col_letter = col[0].column_letter
        for cell in col:
            try:
                if cell.value is not None:
                    max_len = max(max_len, len(str(cell.value)))
            except Exception:
                pass
        ws.column_dimensions[col_letter].width = min(max_len + 2, 30)

    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer


# ============================================================
# DASHBOARD STATS (NEW)
# ============================================================

def get_attendance_stats(user) -> dict[str, Any]:
    """
    Aggregate counts for dashboard cards.
    Respects department scoping for HOD users.
    """
    dept_id = scoped_department_id(user)

    base_where: dict[str, Any] = {}
    if dept_id:
        base_where["employee"] = {"is": {"departmentId": dept_id}}

    total_records = db.attendanceraw.count(where=base_where)
    verified_records = db.attendanceraw.count(
        where={**base_where, "verifiedAt": {"not": None}}
    )
    unverified_records = total_records - verified_records

    anomaly_where: dict[str, Any] = {"resolved": False}
    if dept_id:
        anomaly_where["attendanceRaw"] = {
            "is": {"employee": {"is": {"departmentId": dept_id}}}
        }
    unresolved_anomalies = db.anomaly.count(where=anomaly_where)

    status_breakdown: dict[str, int] = {}
    for status in ["W", "A", "LV", "#", "L", "E", "OT1", "OT2", "OT3"]:
        count = db.attendanceraw.count(
            where={**base_where, "status": status}
        )
        if count > 0:
            status_breakdown[status] = count

    recent_batch = db.attendancebatch.find_first(order={"createdAt": "desc"})
    recent_batch_payload = None
    if recent_batch:
        recent_batch_payload = {
            "id": recent_batch.id,
            "filename": recent_batch.filename,
            "rowCount": recent_batch.rowCount,
            "insertedCount": getattr(recent_batch, "insertedCount", 0),
            "duplicateCount": getattr(recent_batch, "duplicateCount", 0),
            "anomalyCount": getattr(recent_batch, "anomalyCount", 0),
            "createdAt": (
                recent_batch.createdAt.isoformat()
                if recent_batch.createdAt
                else None
            ),
        }

    total_batches = db.attendancebatch.count()

    return {
        "total_records": total_records,
        "verified_records": verified_records,
        "unverified_records": unverified_records,
        "unresolved_anomalies": unresolved_anomalies,
        "status_breakdown": status_breakdown,
        "total_batches": total_batches,
        "recent_batch": recent_batch_payload,
    }


# ============================================================
# PRIVATE HELPERS
# ============================================================

def _upsert_employees_and_departments(rows: list[dict[str, Any]]) -> dict[str, str]:
    dept_ids: dict[str, str] = {}
    employee_ids: dict[str, str] = {}
    latest_by_person: dict[str, dict[str, Any]] = {}
    for row in rows:
        latest_by_person[row["Person ID"]] = row

    for person_id, row in latest_by_person.items():
        dept_id = None
        dept_name = row.get("Department")
        if dept_name:
            if dept_name not in dept_ids:
                dept = db.department.upsert(
                    where={"name": dept_name},
                    data={"create": {"name": dept_name}, "update": {}},
                )
                dept_ids[dept_name] = dept.id
            dept_id = dept_ids[dept_name]

        employee = db.employee.upsert(
            where={"personId": person_id},
            data={
                "create": {
                    "personId": person_id,
                    "fullName": row.get("Name") or person_id,
                    "departmentId": dept_id,
                    "position": row.get("Position"),
                    "gender": row.get("Gender"),
                },
                "update": {
                    "fullName": row.get("Name") or person_id,
                    "departmentId": dept_id,
                    "position": row.get("Position"),
                    "gender": row.get("Gender"),
                },
            },
        )
        employee_ids[person_id] = employee.id

    return employee_ids


def _to_raw_record(
    row: dict[str, Any], employee_id: str, batch_id: str
) -> dict[str, Any]:
    no = row.get("No.")
    dt = row["Date"].to_pydatetime()
    return {
        "batchId": batch_id,
        "employeeId": employee_id,
        "rowNo": int(no) if no is not None else None,
        "date": date_only(dt),
        "week": row.get("Week"),
        "timetable": row.get("Timetable"),
        "checkIn": row.get("Check-in"),
        "checkOut": row.get("Check-out"),
        "workMin": row["Work"],
        "otMin": row["OT"],
        "attendedMin": row["Attended"],
        "lateMin": row["Late"],
        "earlyMin": row["Early"],
        "absentMin": row["Absent"],
        "leaveMin": row["Leave"],
        "status": row.get("Status") or "-",
        "records": row.get("Records"),
    }


def _dedupe_payload(
    payload: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], int]:
    """Keep the last row per (employee, date); return (rows, number dropped)."""
    by_key: dict[tuple[str, Any], dict[str, Any]] = {}
    for item in payload:
        by_key[(item["employeeId"], item["date"].date())] = item
    return list(by_key.values()), len(payload) - len(by_key)


def _existing_raw_by_key(
    payload: list[dict[str, Any]],
) -> dict[tuple[str, Any], Any]:
    if not payload:
        return {}
    employee_ids = list({p["employeeId"] for p in payload})
    dates = [p["date"] for p in payload]
    found = db.attendanceraw.find_many(
        where={
            "employeeId": {"in": employee_ids},
            "date": {"gte": min(dates), "lte": max(dates)},
        }
    )
    return {(r.employeeId, r.date.date()): r for r in found}


def _plan_import(payload: list[dict[str, Any]], existing: dict[tuple[str, Any], Any]):
    """
    Split parsed rows into: brand new rows, existing unverified rows to
    refresh, and count of existing verified rows that must not be touched.
    """
    to_create: list[dict[str, Any]] = []
    to_refresh: list[tuple[str, dict[str, Any]]] = []
    skipped_verified = 0
    for item in payload:
        current = existing.get((item["employeeId"], item["date"].date()))
        if current is None:
            to_create.append(item)
        elif getattr(current, "verifiedAt", None) is not None:
            skipped_verified += 1
        else:
            to_refresh.append((current.id, item))
    return to_create, to_refresh, skipped_verified


def _anomaly(
    batch_id: str, raw_id: str, type_: str, message: str
) -> dict[str, Any]:
    return {
        "batchId": batch_id,
        "attendanceRawId": raw_id,
        "type": type_,
        "message": message,
    }


def _snapshot(record) -> dict[str, Any]:
    return {
        "check_in": record.checkIn,
        "check_out": record.checkOut,
        "work_min": record.workMin,
        "ot_min": record.otMin,
        "attended_min": record.attendedMin,
        "late_min": record.lateMin,
        "early_min": record.earlyMin,
        "absent_min": record.absentMin,
        "leave_min": record.leaveMin,
        "status": record.status,
        "notes": getattr(record, "notes", None),
    }


def _upsert_final(raw, user_id: str) -> None:
    payload = {
        "attendanceRawId": raw.id,
        "employeeId": raw.employeeId,
        "rowNo": raw.rowNo,
        "date": raw.date,
        "week": raw.week,
        "timetable": raw.timetable,
        "checkIn": raw.checkIn,
        "checkOut": raw.checkOut,
        "workMin": raw.workMin,
        "otMin": raw.otMin,
        "attendedMin": raw.attendedMin,
        "lateMin": raw.lateMin,
        "earlyMin": raw.earlyMin,
        "absentMin": raw.absentMin,
        "leaveMin": raw.leaveMin,
        "status": raw.status,
        "records": raw.records,
        "notes": raw.notes,
        "verifiedById": user_id,
        "verifiedAt": utcnow(),
    }
    existing = db.attendancefinal.find_first(
        where={
            "OR": [
                {"attendanceRawId": raw.id},
                {"employeeId": raw.employeeId, "date": raw.date},
            ]
        }
    )
    if existing:
        db.attendancefinal.update(where={"id": existing.id}, data=payload)
    else:
        db.attendancefinal.create(data=payload)


def _assert_can_view_employee(user, employee) -> None:
    if role_str(user.role) != "HOD":
        return
    dept_id = scoped_department_id(user)
    if employee and employee.departmentId != dept_id:
        raise AppError("You can only access your own department", 403)