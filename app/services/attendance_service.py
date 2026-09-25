"""
Spec sections 3.3 (steps 2-5) and 5.1-5.3:
upload -> raw database -> anomaly checker -> HR verify/edit -> attendance_final.
"""
from __future__ import annotations

from typing import Any

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


def import_attendance_file(filename: str, data: bytes, uploaded_by_id: str) -> dict[str, Any]:
    if not filename or not filename.lower().endswith(ALLOWED_EXTENSIONS):
        raise AppError(f"Unsupported file type. Allowed: {', '.join(ALLOWED_EXTENSIONS)}", 400)

    rows = parse_attendance_file(filename, data)
    employee_ids = _upsert_employees_and_departments(rows)

    batch = db.attendancebatch.create(
        data={
            "filename": filename,
            "uploadedById": uploaded_by_id,
            "rowCount": len(rows),
        }
    )

    raw_payload = [_to_raw_record(row, employee_ids[row["Person ID"]], batch.id) for row in rows]
    create_result = db.attendanceraw.create_many(data=raw_payload, skip_duplicates=True)
    inserted_count = create_result if isinstance(create_result, int) else create_result.count
    duplicate_count = len(raw_payload) - inserted_count

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
        "duplicateCount": batch.duplicateCount,
        "anomalyCount": batch.anomalyCount,
    }


def list_batches(limit: int = 50):
    return db.attendancebatch.find_many(order={"createdAt": "desc"}, take=limit)


def list_raw_records(
    user,
    *,
    batch_id: str | None = None,
    department_id: str | None = None,
    office: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    status: str | None = None,
    unverified_only: bool = False,
    take: int = 200,
    skip: int = 0,
):
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

    return db.attendanceraw.find_many(
        where=where,
        include=_EMPLOYEE_INCLUDE,
        order={"date": "asc"},
        take=min(take, 500),
        skip=max(skip, 0),
    )


def get_raw_record(raw_id: str, user):
    record = db.attendanceraw.find_unique(where={"id": raw_id}, include=_EMPLOYEE_INCLUDE)
    if record is None:
        raise AppError("Attendance record not found", 404)
    _assert_can_view_employee(user, record.employee)
    return record


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
            data={"resolved": True, "resolvedById": user.id, "resolvedAt": utcnow()},
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


def resolve_anomaly(anomaly_id: str, user, note: str | None = None):
    anomaly = db.anomaly.find_unique(where={"id": anomaly_id})
    if anomaly is None:
        raise AppError("Anomaly not found", 404)
    if anomaly.resolved:
        return anomaly

    updated = db.anomaly.update(
        where={"id": anomaly_id},
        data={"resolved": True, "resolvedById": user.id, "resolvedAt": utcnow()},
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


def list_anomalies(user, *, batch_id: str | None = None, resolved: bool | None = False, take: int = 200):
    where: dict[str, Any] = {}
    if batch_id:
        where["batchId"] = batch_id
    if resolved is False:
        where["resolved"] = False
    elif resolved is True:
        where["resolved"] = True

    dept_id = scoped_department_id(user)
    if dept_id:
        where["attendanceRaw"] = {"is": {"employee": {"is": {"departmentId": dept_id}}}}

    return db.anomaly.find_many(
        where=where,
        include={"attendanceRaw": {"include": _EMPLOYEE_INCLUDE}},
        order={"createdAt": "asc"},
        take=min(take, 500),
    )


def list_final_records(user, **filters):
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

    return db.attendancefinal.find_many(
        where=where,
        include=_EMPLOYEE_INCLUDE,
        order={"date": "asc"},
        take=min(int(filters.get("take") or 200), 500),
        skip=max(int(filters.get("skip") or 0), 0),
    )


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
                    _anomaly(batch_id, r.id, "NEGATIVE_VALUE", f"{label} minutes is negative ({value})")
                )

        no_checkin = not r.checkIn or r.checkIn == "-"
        no_checkout = not r.checkOut or r.checkOut == "-"
        if status not in EXEMPT_STATUSES and status not in ABSENT_STATUSES and (no_checkin or no_checkout):
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
                _anomaly(batch_id, r.id, "ABSENT_INCONSISTENCY", "Status is 'A' (Absent) but absent minutes is 0")
            )
        if status not in ABSENT_STATUSES and status not in EXEMPT_STATUSES and r.absentMin > 0:
            anomalies.append(
                _anomaly(
                    batch_id,
                    r.id,
                    "ABSENT_INCONSISTENCY",
                    f"Status is '{r.status}' but absent minutes is {r.absentMin}",
                )
            )

    return anomalies


def apply_leave_to_days(employee_id: str, dates: list, user_id: str, leave_type: str, reason: str | None) -> int:
    """Mark each date as LV on raw (if present) and upsert attendance_final."""
    updated = 0
    note = f"Leave ({leave_type})" + (f": {reason}" if reason else "")
    for day in dates:
        raw = db.attendanceraw.find_first(where={"employeeId": employee_id, "date": day})
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
            updated_raw = db.attendanceraw.update(where={"id": raw.id}, data=payload)
            db.anomaly.update_many(
                where={"attendanceRawId": raw.id, "resolved": False},
                data={"resolved": True, "resolvedById": user_id, "resolvedAt": utcnow()},
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
        "verified_at": record.verifiedAt.isoformat() if getattr(record, "verifiedAt", None) else None,
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


def _to_raw_record(row: dict[str, Any], employee_id: str, batch_id: str) -> dict[str, Any]:
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


def _anomaly(batch_id: str, raw_id: str, type_: str, message: str) -> dict[str, Any]:
    return {"batchId": batch_id, "attendanceRawId": raw_id, "type": type_, "message": message}


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
    existing = db.attendancefinal.find_first(where={"OR": [{"attendanceRawId": raw.id}, {"employeeId": raw.employeeId, "date": raw.date}]})
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
