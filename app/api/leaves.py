from flask import Blueprint, g, jsonify, request

from ..schemas.attendance import LeaveCreateIn
from ..services import leave_service
from ..utils.decorators import auth_required

bp = Blueprint("leaves", __name__, url_prefix="/api/leaves")


@bp.post("")
@auth_required("ADMIN", "HOD")
def create_leave():
    """Add leave. Admin: any employee. HOD: own department only. Marks days as LV
    ---
    tags: [Leaves]
    security: [{Bearer: []}]
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required: [employee_id, leave_type, start_date, end_date]
          properties:
            employee_id: {type: string}
            leave_type:
              type: string
              enum: [ANNUAL, SICK, BUSINESS_TRIP, MATERNITY, PATERNITY, UNPAID]
            start_date: {type: string, description: "YYYY-MM-DD"}
            end_date: {type: string, description: "YYYY-MM-DD"}
            reason: {type: string}
    responses:
      201: {description: Leave created}
    """
    body = LeaveCreateIn.model_validate(request.get_json(silent=True) or {})
    return jsonify(leave_service.create_leave(g.user, body)), 201


@bp.get("")
@auth_required("ADMIN", "HOD", "DIRECTOR")
def list_leaves():
    """List leave records, optionally filtered by employee or department
    ---
    tags: [Leaves]
    security: [{Bearer: []}]
    parameters:
      - in: query
        name: employee_id
        type: string
      - in: query
        name: department_id
        type: string
    responses:
      200: {description: List of leave records}
    """
    return jsonify(
        leave_service.list_leaves(
            g.user,
            employee_id=request.args.get("employee_id"),
            department_id=request.args.get("department_id"),
        )
    )