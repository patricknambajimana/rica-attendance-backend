from ..extensions import db
from ..schemas.attendance import DepartmentCreateIn, DepartmentUpdateIn, HolidayCreateIn, ShiftCreateIn, ShiftUpdateIn
from ..utils.audit import log_action
from ..utils.dates import parse_iso_date
from ..utils.errors import AppError
from ..utils.scope import scoped_department_id


def list_departments():
    return db.department.find_many(order={"name": "asc"})


def create_department(user, body: DepartmentCreateIn):
    existing = db.department.find_unique(where={"name": body.name.strip()})
    if existing:
        raise AppError("Department already exists", 409)
    dept = db.department.create(data={"name": body.name.strip(), "office": body.office})
    log_action("MANAGE_CONFIG", user_id=user.id, entity_type="Department", entity_id=dept.id, delta={"name": dept.name})
    return serialize_department(dept)


def update_department(user, department_id: str, body: DepartmentUpdateIn):
    dept = db.department.find_unique(where={"id": department_id})
    if dept is None:
        raise AppError("Department not found", 404)
    data = {}
    if "name" in body.model_fields_set and body.name:
        clash = db.department.find_unique(where={"name": body.name.strip()})
        if clash and clash.id != department_id:
            raise AppError("Department name already in use", 409)
        data["name"] = body.name.strip()
    if "office" in body.model_fields_set:
        data["office"] = body.office
    updated = db.department.update(where={"id": department_id}, data=data)
    log_action("MANAGE_CONFIG", user_id=user.id, entity_type="Department", entity_id=department_id, delta=data)
    return serialize_department(updated)


def serialize_department(dept) -> dict:
    return {"id": dept.id, "name": dept.name, "office": dept.office, "created_at": dept.createdAt.isoformat() if dept.createdAt else None}


def list_employees(user, department_id: str | None = None, office: str | None = None):
    dept_id = scoped_department_id(user, department_id)
    where: dict = {}
    if dept_id:
        where["departmentId"] = dept_id
    if office:
        where["department"] = {"is": {"office": office}}
    rows = db.employee.find_many(
        where=where,
        include={"department": True},
        order={"fullName": "asc"},
        take=1000,
    )
    return [serialize_employee(e) for e in rows]


def serialize_employee(emp) -> dict:
    dept = emp.department if getattr(emp, "department", None) else None
    return {
        "id": emp.id,
        "person_id": emp.personId,
        "full_name": emp.fullName,
        "department_id": emp.departmentId,
        "department": dept.name if dept else None,
        "office": dept.office if dept else None,
        "position": emp.position,
        "gender": emp.gender,
        "is_active": emp.isActive,
    }


def list_shifts():
    return [
        serialize_shift(s) for s in db.shift.find_many(order={"name": "asc"})
    ]


def create_shift(user, body: ShiftCreateIn):
    existing = db.shift.find_unique(where={"name": body.name.strip()})
    if existing:
        raise AppError("Shift name already exists", 409)
    shift = db.shift.create(
        data={
            "name": body.name.strip(),
            "startTime": body.start_time,
            "endTime": body.end_time,
            "workMinutes": body.work_minutes,
            "createdById": user.id,
        }
    )
    log_action("MANAGE_CONFIG", user_id=user.id, entity_type="Shift", entity_id=shift.id)
    return serialize_shift(shift)


def update_shift(user, shift_id: str, body: ShiftUpdateIn):
    shift = db.shift.find_unique(where={"id": shift_id})
    if shift is None:
        raise AppError("Shift not found", 404)
    data = {}
    mapping = {
        "name": "name",
        "start_time": "startTime",
        "end_time": "endTime",
        "work_minutes": "workMinutes",
        "is_active": "isActive",
    }
    for api, prisma in mapping.items():
        if api in body.model_fields_set:
            value = getattr(body, api)
            data[prisma] = value.strip() if isinstance(value, str) else value
    updated = db.shift.update(where={"id": shift_id}, data=data)
    log_action("MANAGE_CONFIG", user_id=user.id, entity_type="Shift", entity_id=shift_id, delta=data)
    return serialize_shift(updated)


def serialize_shift(shift) -> dict:
    return {
        "id": shift.id,
        "name": shift.name,
        "start_time": shift.startTime,
        "end_time": shift.endTime,
        "work_minutes": shift.workMinutes,
        "is_active": shift.isActive,
    }


def list_holidays():
    return [serialize_holiday(h) for h in db.holiday.find_many(order={"date": "asc"})]


def create_holiday(user, body: HolidayCreateIn):
    day = parse_iso_date(body.date, "date")
    existing = db.holiday.find_unique(where={"date": day})
    if existing:
        raise AppError("A holiday already exists on that date", 409)
    holiday = db.holiday.create(
        data={"date": day, "name": body.name.strip(), "isRecurring": body.is_recurring, "createdById": user.id}
    )
    log_action("MANAGE_CONFIG", user_id=user.id, entity_type="Holiday", entity_id=holiday.id)
    return serialize_holiday(holiday)


def delete_holiday(user, holiday_id: str):
    holiday = db.holiday.find_unique(where={"id": holiday_id})
    if holiday is None:
        raise AppError("Holiday not found", 404)
    db.holiday.delete(where={"id": holiday_id})
    log_action("MANAGE_CONFIG", user_id=user.id, entity_type="Holiday", entity_id=holiday_id, delta={"deleted": True})


def serialize_holiday(holiday) -> dict:
    return {
        "id": holiday.id,
        "date": holiday.date.date().isoformat(),
        "name": holiday.name,
        "is_recurring": holiday.isRecurring,
    }
