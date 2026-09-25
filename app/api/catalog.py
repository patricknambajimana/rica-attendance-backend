from flask import Blueprint, g, jsonify, request

from ..schemas.attendance import DepartmentCreateIn, DepartmentUpdateIn, HolidayCreateIn, ShiftCreateIn, ShiftUpdateIn
from ..services import catalog_service
from ..utils.decorators import auth_required

bp = Blueprint("catalog", __name__, url_prefix="/api")


@bp.get("/departments")
@auth_required()
def list_departments():
    return jsonify([catalog_service.serialize_department(d) for d in catalog_service.list_departments()])


@bp.post("/departments")
@auth_required("ADMIN")
def create_department():
    body = DepartmentCreateIn.model_validate(request.get_json(silent=True) or {})
    return jsonify(catalog_service.create_department(g.user, body)), 201


@bp.patch("/departments/<department_id>")
@auth_required("ADMIN")
def update_department(department_id: str):
    body = DepartmentUpdateIn.model_validate(request.get_json(silent=True) or {})
    return jsonify(catalog_service.update_department(g.user, department_id, body))


@bp.get("/employees")
@auth_required()
def list_employees():
    return jsonify(
        catalog_service.list_employees(
            g.user,
            request.args.get("department_id"),
            request.args.get("office"),
        )
    )


@bp.get("/shifts")
@auth_required()
def list_shifts():
    return jsonify(catalog_service.list_shifts())


@bp.post("/shifts")
@auth_required("ADMIN")
def create_shift():
    body = ShiftCreateIn.model_validate(request.get_json(silent=True) or {})
    return jsonify(catalog_service.create_shift(g.user, body)), 201


@bp.patch("/shifts/<shift_id>")
@auth_required("ADMIN")
def update_shift(shift_id: str):
    body = ShiftUpdateIn.model_validate(request.get_json(silent=True) or {})
    return jsonify(catalog_service.update_shift(g.user, shift_id, body))


@bp.get("/holidays")
@auth_required()
def list_holidays():
    return jsonify(catalog_service.list_holidays())


@bp.post("/holidays")
@auth_required("ADMIN")
def create_holiday():
    body = HolidayCreateIn.model_validate(request.get_json(silent=True) or {})
    return jsonify(catalog_service.create_holiday(g.user, body)), 201


@bp.delete("/holidays/<holiday_id>")
@auth_required("ADMIN")
def delete_holiday(holiday_id: str):
    catalog_service.delete_holiday(g.user, holiday_id)
    return jsonify(message="Holiday deleted")
