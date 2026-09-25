from ..extensions import db
from ..schemas.attendance import LeaveCreateIn
from ..utils.audit import log_action
from ..utils.dates import iter_dates, parse_iso_date
from ..utils.errors import AppError
from ..utils.scope import scoped_department_id
from ..utils.validators import role_str
from .attendance_service import apply_leave_to_days


def create_leave(user, body: LeaveCreateIn) -> dict:
    start = parse_iso_date(body.start_date, "start_date")
    end = parse_iso_date(body.end_date, "end_date")
    if end < start:
        raise AppError("end_date must be on or after start_date", 400)

    employee = db.employee.find_unique(where={"id": body.employee_id}, include={"department": True})
    if employee is None:
        raise AppError("Employee not found", 404)

    if role_str(user.role) == "HOD":
        dept_id = scoped_department_id(user)
        if employee.departmentId != dept_id:
            raise AppError("You can only add leave for employees in your department", 403)

    leave = db.leave.create(
        data={
            "employeeId": employee.id,
            "leaveType": body.leave_type,
            "startDate": start,
            "endDate": end,
            "reason": body.reason,
            "createdById": user.id,
        }
    )

    days = list(iter_dates(start, end))
    applied = apply_leave_to_days(employee.id, days, user.id, body.leave_type, body.reason)

    log_action(
        "ADD_LEAVE",
        user_id=user.id,
        entity_type="Leave",
        entity_id=leave.id,
        delta={
            "employeeId": employee.id,
            "leaveType": body.leave_type,
            "startDate": body.start_date,
            "endDate": body.end_date,
            "daysApplied": applied,
        },
    )
    return serialize_leave(leave, employee)


def list_leaves(user, employee_id: str | None = None, department_id: str | None = None):
    dept_id = scoped_department_id(user, department_id)
    where: dict = {}
    if employee_id:
        where["employeeId"] = employee_id
    if dept_id:
        where["employee"] = {"is": {"departmentId": dept_id}}

    leaves = db.leave.find_many(
        where=where,
        include={"employee": {"include": {"department": True}}},
        order={"startDate": "desc"},
        take=200,
    )
    return [serialize_leave(item, item.employee) for item in leaves]


def serialize_leave(leave, employee=None) -> dict:
    emp = employee or getattr(leave, "employee", None)
    dept = getattr(emp, "department", None) if emp else None
    return {
        "id": leave.id,
        "employee_id": leave.employeeId,
        "person_id": emp.personId if emp else None,
        "name": emp.fullName if emp else None,
        "department": dept.name if dept else None,
        "leave_type": str(getattr(leave.leaveType, "value", leave.leaveType)),
        "start_date": leave.startDate.date().isoformat(),
        "end_date": leave.endDate.date().isoformat(),
        "reason": leave.reason,
        "created_by_id": leave.createdById,
        "created_at": leave.createdAt.isoformat() if leave.createdAt else None,
    }
