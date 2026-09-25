from flask import Blueprint, g, jsonify, request

from ..schemas.attendance import LeaveCreateIn
from ..services import leave_service
from ..utils.decorators import auth_required

bp = Blueprint("leaves", __name__, url_prefix="/api/leaves")


@bp.post("")
@auth_required("ADMIN", "HOD")
def create_leave():
    """Add leave. Admin: any employee. HOD: own department only. Marks days as LV."""
    body = LeaveCreateIn.model_validate(request.get_json(silent=True) or {})
    return jsonify(leave_service.create_leave(g.user, body)), 201


@bp.get("")
@auth_required("ADMIN", "HOD", "DIRECTOR")
def list_leaves():
    return jsonify(
        leave_service.list_leaves(
            g.user,
            employee_id=request.args.get("employee_id"),
            department_id=request.args.get("department_id"),
        )
    )
