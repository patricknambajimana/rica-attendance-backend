from __future__ import annotations

from calendar import monthrange
from datetime import datetime

from ..extensions import db
from ..utils.audit import log_action
from ..utils.dates import date_range_filter, iter_dates, parse_iso_date
from ..utils.errors import AppError
from ..utils.scope import scoped_department_id
from .attendance_service import ATTENDED_STATUSES, serialize_raw

DIRECTOR_COLUMNS = (
    "No.",
    "Name",
    "Department",
    "Date",
    "Week",
    "Timetable",
    "Check-in",
    "Check-out",
)


def _rating(attendance_pct: float) -> str:
    if attendance_pct >= 95:
        return "Excellent"
    if attendance_pct >= 85:
        return "Good"
    if attendance_pct >= 70:
        return "Needs Improvement"
    return "Warning"


def _employee_where(user, department_id: str | None, office: str | None) -> dict:
    dept_id = scoped_department_id(user, department_id)
    filt: dict = {}
    if dept_id:
        filt["departmentId"] = dept_id
    if office:
        filt["department"] = {"is": {"office": office}}
    return filt


def _load_effective_records(user, date_from: str, date_to: str, department_id: str | None, office: str | None):
    date_filt = date_range_filter(date_from, date_to)
    emp_filter = _employee_where(user, department_id, office)
    where: dict = {"date": date_filt} if date_filt else {}
    if emp_filter:
        where["employee"] = {"is": emp_filter}

    raw_rows = db.attendanceraw.find_many(
        where=where,
        include={"employee": {"include": {"department": True}}},
        order={"date": "asc"},
    )
    final_rows = db.attendancefinal.find_many(
        where=where,
        include={"employee": {"include": {"department": True}}},
        order={"date": "asc"},
    )

    by_key: dict[tuple[str, datetime], object] = {}
    for row in raw_rows:
        by_key[(row.employeeId, row.date)] = row
    for row in final_rows:
        by_key[(row.employeeId, row.date)] = row
    return list(by_key.values())


def daily_report(user, report_date: str, department_id: str | None = None, office: str | None = None):
    day = parse_iso_date(report_date, "date")
    records = _load_effective_records(user, report_date, report_date, department_id, office)
    records.sort(key=lambda r: ((r.employee.fullName if r.employee else ""), r.date))

    rows = []
    for idx, record in enumerate(records, start=1):
        emp = record.employee
        dept = emp.department if emp else None
        rows.append(
            {
                "No.": idx,
                "Name": emp.fullName if emp else None,
                "Department": dept.name if dept else None,
                "Date": record.date.date().isoformat(),
                "Week": record.week,
                "Timetable": record.timetable,
                "Check-in": record.checkIn,
                "Check-out": record.checkOut,
                "person_id": emp.personId if emp else None,
                "status": record.status,
                "office": dept.office if dept else None,
            }
        )

    log_action(
        "EXPORT",
        user_id=user.id,
        entity_type="DailyReport",
        delta={"date": report_date, "rows": len(rows), "departmentId": department_id},
    )
    return {"date": day.date().isoformat(), "columns": list(DIRECTOR_COLUMNS), "rows": rows}


def period_report(
    user,
    date_from: str,
    date_to: str,
    department_id: str | None = None,
    office: str | None = None,
):
    records = _load_effective_records(user, date_from, date_to, department_id, office)
    records.sort(key=lambda r: (r.date, r.employee.fullName if r.employee else ""))
    rows = [serialize_raw(r) for r in records]
    log_action(
        "EXPORT",
        user_id=user.id,
        entity_type="PeriodReport",
        delta={"from": date_from, "to": date_to, "rows": len(rows)},
    )
    return {"from": date_from, "to": date_to, "count": len(rows), "rows": rows}


def performance_kpis(
    user,
    date_from: str,
    date_to: str,
    department_id: str | None = None,
    office: str | None = None,
):
    start = parse_iso_date(date_from, "from")
    end = parse_iso_date(date_to, "to")
    if end < start:
        raise AppError("to must be on or after from", 400)

    holidays = db.holiday.find_many()
    holiday_md = {(h.date.month, h.date.day) for h in holidays if h.isRecurring}
    holiday_days = {h.date.date() for h in holidays if not h.isRecurring}

    working_days = 0
    for day in iter_dates(start, end):
        if day.weekday() >= 5:
            continue
        if day.date() in holiday_days or (day.month, day.day) in holiday_md:
            continue
        working_days += 1

    records = _load_effective_records(user, date_from, date_to, department_id, office)
    by_employee: dict[str, list] = {}
    for record in records:
        by_employee.setdefault(record.employeeId, []).append(record)

    employees = []
    for emp_id, emp_rows in by_employee.items():
        emp = emp_rows[0].employee
        dept = emp.department if emp else None
        present_days = 0
        punctual_days = 0
        late_days = 0
        leave_days = 0
        absent_days = 0

        for row in emp_rows:
            status = (row.status or "").upper()
            if status == "#":
                continue
            if day_skipped_as_non_working(row.date, holiday_days, holiday_md):
                continue
            if status == "LV":
                leave_days += 1
                continue
            if status in ATTENDED_STATUSES or (row.attendedMin or 0) > 0:
                present_days += 1
                if (row.lateMin or 0) <= 0:
                    punctual_days += 1
                else:
                    late_days += 1
            elif status == "A":
                absent_days += 1

        denom = working_days or 1
        attendance_pct = round((present_days / denom) * 100, 2) if working_days else 0.0
        punctuality_pct = round((punctual_days / present_days) * 100, 2) if present_days else 0.0
        employees.append(
            {
                "employee_id": emp_id,
                "person_id": emp.personId if emp else None,
                "name": emp.fullName if emp else None,
                "department": dept.name if dept else None,
                "office": dept.office if dept else None,
                "working_days": working_days,
                "days_present": present_days,
                "days_punctual": punctual_days,
                "days_late": late_days,
                "days_leave": leave_days,
                "days_absent": absent_days,
                "attendance_pct": attendance_pct,
                "punctuality_pct": punctuality_pct,
                "rating": _rating(attendance_pct),
            }
        )

    employees.sort(key=lambda e: e["name"] or "")
    summary = {
        "employee_count": len(employees),
        "working_days": working_days,
        "average_attendance_pct": round(
            sum(e["attendance_pct"] for e in employees) / len(employees), 2
        )
        if employees
        else 0,
        "average_punctuality_pct": round(
            sum(e["punctuality_pct"] for e in employees) / len(employees), 2
        )
        if employees
        else 0,
    }
    log_action(
        "EXPORT",
        user_id=user.id,
        entity_type="KpiReport",
        delta={"from": date_from, "to": date_to, "employees": len(employees)},
    )
    return {
        "from": date_from,
        "to": date_to,
        "formulas": {
            "attendance_pct": "(Days Present / Working Days) * 100",
            "punctuality_pct": "(Days with no late minutes / Days Present) * 100",
            "thresholds": {
                "Excellent": ">= 95%",
                "Good": "85-94%",
                "Needs Improvement": "70-84%",
                "Warning": "< 70%",
            },
        },
        "summary": summary,
        "employees": employees,
    }


def month_bounds(year: int, month: int) -> tuple[str, str]:
    last = monthrange(year, month)[1]
    return f"{year:04d}-{month:02d}-01", f"{year:04d}-{month:02d}-{last:02d}"


def quarter_bounds(year: int, quarter: int) -> tuple[str, str]:
    if quarter not in (1, 2, 3, 4):
        raise AppError("quarter must be 1-4", 400)
    start_month = (quarter - 1) * 3 + 1
    end_month = start_month + 2
    last = monthrange(year, end_month)[1]
    return f"{year:04d}-{start_month:02d}-01", f"{year:04d}-{end_month:02d}-{last:02d}"


def year_bounds(year: int) -> tuple[str, str]:
    return f"{year:04d}-01-01", f"{year:04d}-12-31"


def day_skipped_as_non_working(dt: datetime, holiday_days, holiday_md) -> bool:
    if dt.weekday() >= 5:
        return True
    if dt.date() in holiday_days or (dt.month, dt.day) in holiday_md:
        return True
    return False


def records_to_csv(rows: list[dict], columns: tuple[str, ...] | list[str]) -> str:
    import csv
    from io import StringIO

    buf = StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(columns), extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue()
