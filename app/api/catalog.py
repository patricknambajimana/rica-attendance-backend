from flask import Blueprint, g, jsonify, request

from ..schemas.attendance import DepartmentCreateIn, DepartmentUpdateIn, HolidayCreateIn, ShiftCreateIn, ShiftUpdateIn
from ..services import catalog_service
from ..utils.decorators import auth_required

bp = Blueprint("catalog", __name__, url_prefix="/api")


@bp.get("/departments")
@auth_required()
def list_departments():
    """List all departments
    ---
    tags: [Catalog]
    security: [{Bearer: []}]
    responses:
      200: {description: List of departments}
    """
    return jsonify([catalog_service.serialize_department(d) for d in catalog_service.list_departments()])


@bp.post("/departments")
@auth_required("ADMIN")
def create_department():
    """Create a department
    ---
    tags: [Catalog]
    security: [{Bearer: []}]
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required: [name]
          properties:
            name: {type: string}
            office: {type: string}
    responses:
      201: {description: Department created}
    """
    body = DepartmentCreateIn.model_validate(request.get_json(silent=True) or {})
    return jsonify(catalog_service.create_department(g.user, body)), 201


@bp.patch("/departments/<department_id>")
@auth_required("ADMIN")
def update_department(department_id: str):
    """Update a department
    ---
    tags: [Catalog]
    security: [{Bearer: []}]
    parameters:
      - in: path
        name: department_id
        type: string
        required: true
      - in: body
        name: body
        schema:
          type: object
          properties:
            name: {type: string}
            office: {type: string}
    responses:
      200: {description: Updated department}
    """
    body = DepartmentUpdateIn.model_validate(request.get_json(silent=True) or {})
    return jsonify(catalog_service.update_department(g.user, department_id, body))


@bp.get("/employees")
@auth_required()
def list_employees():
    """List employees, optionally filtered by department or office
    ---
    tags: [Catalog]
    security: [{Bearer: []}]
    parameters:
      - in: query
        name: department_id
        type: string
      - in: query
        name: office
        type: string
    responses:
      200: {description: List of employees}
    """
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
    """List all shifts
    ---
    tags: [Catalog]
    security: [{Bearer: []}]
    responses:
      200: {description: List of shifts}
    """
    return jsonify(catalog_service.list_shifts())


@bp.post("/shifts")
@auth_required("ADMIN")
def create_shift():
    """Create a shift
    ---
    tags: [Catalog]
    security: [{Bearer: []}]
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required: [name, start_time, end_time, work_minutes]
          properties:
            name: {type: string}
            start_time: {type: string, description: "e.g. 08:00"}
            end_time: {type: string, description: "e.g. 17:00"}
            work_minutes: {type: integer}
    responses:
      201: {description: Shift created}
    """
    body = ShiftCreateIn.model_validate(request.get_json(silent=True) or {})
    return jsonify(catalog_service.create_shift(g.user, body)), 201


@bp.patch("/shifts/<shift_id>")
@auth_required("ADMIN")
def update_shift(shift_id: str):
    """Update a shift
    ---
    tags: [Catalog]
    security: [{Bearer: []}]
    parameters:
      - in: path
        name: shift_id
        type: string
        required: true
      - in: body
        name: body
        schema:
          type: object
          properties:
            name: {type: string}
            start_time: {type: string}
            end_time: {type: string}
            work_minutes: {type: integer}
            is_active: {type: boolean}
    responses:
      200: {description: Updated shift}
    """
    body = ShiftUpdateIn.model_validate(request.get_json(silent=True) or {})
    return jsonify(catalog_service.update_shift(g.user, shift_id, body))


@bp.get("/holidays")
@auth_required()
def list_holidays():
    """List all holidays
    ---
    tags: [Catalog]
    security: [{Bearer: []}]
    responses:
      200: {description: List of holidays}
    """
    return jsonify(catalog_service.list_holidays())


@bp.post("/holidays")
@auth_required("ADMIN")
def create_holiday():
    """Create a holiday
    ---
    tags: [Catalog]
    security: [{Bearer: []}]
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required: [date, name]
          properties:
            date: {type: string, description: "YYYY-MM-DD"}
            name: {type: string}
            is_recurring: {type: boolean, default: false}
    responses:
      201: {description: Holiday created}
    """
    body = HolidayCreateIn.model_validate(request.get_json(silent=True) or {})
    return jsonify(catalog_service.create_holiday(g.user, body)), 201


@bp.delete("/holidays/<holiday_id>")
@auth_required("ADMIN")
def delete_holiday(holiday_id: str):
    """Delete a holiday
    ---
    tags: [Catalog]
    security: [{Bearer: []}]
    parameters:
      - in: path
        name: holiday_id
        type: string
        required: true
    responses:
      200: {description: Holiday deleted}
    """
    catalog_service.delete_holiday(g.user, holiday_id)
    return jsonify(message="Holiday deleted")