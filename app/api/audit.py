from flask import Blueprint, jsonify, request

from ..extensions import db
from ..utils.decorators import auth_required

bp = Blueprint("audit", __name__, url_prefix="/api/audit-logs")


@bp.get("")
@auth_required("ADMIN")
def list_audit_logs():
    """List audit log entries, most recent first
    ---
    tags: [Audit]
    security: [{Bearer: []}]
    parameters:
      - in: query
        name: action
        type: string
      - in: query
        name: user_id
        type: string
      - in: query
        name: take
        type: integer
        default: 100
      - in: query
        name: skip
        type: integer
        default: 0
    responses:
      200: {description: List of audit log entries}
    """
    where = {}
    if request.args.get("action"):
        where["action"] = request.args["action"]
    if request.args.get("user_id"):
        where["userId"] = request.args["user_id"]

    logs = db.auditlog.find_many(
        where=where,
        order={"createdAt": "desc"},
      include={"user": True},
        take=min(int(request.args.get("take", 100)), 500),
        skip=max(int(request.args.get("skip", 0)), 0),
    )
    return jsonify(
        [
            {
                "id": log.id,
                "user_id": log.userId,
                "user_name": log.user.fullName if log.user else None,
                "user_username": log.user.username if log.user else None,
                "user_email": log.user.email if log.user else None,
                "action": log.action,
                "entity_type": log.entityType,
                "entity_id": log.entityId,
                "delta": log.delta,
                "created_at": log.createdAt.isoformat() if log.createdAt else None,
            }
            for log in logs
        ]
    )