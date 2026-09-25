from flask import Blueprint, jsonify, request

from ..extensions import db
from ..utils.decorators import auth_required

bp = Blueprint("audit", __name__, url_prefix="/api/audit-logs")


@bp.get("")
@auth_required("ADMIN")
def list_audit_logs():
    where = {}
    if request.args.get("action"):
        where["action"] = request.args["action"]
    if request.args.get("user_id"):
        where["userId"] = request.args["user_id"]

    logs = db.auditlog.find_many(
        where=where,
        order={"createdAt": "desc"},
        take=min(int(request.args.get("take", 100)), 500),
        skip=max(int(request.args.get("skip", 0)), 0),
    )
    return jsonify(
        [
            {
                "id": log.id,
                "user_id": log.userId,
                "action": log.action,
                "entity_type": log.entityType,
                "entity_id": log.entityId,
                "delta": log.delta,
                "created_at": log.createdAt.isoformat() if log.createdAt else None,
            }
            for log in logs
        ]
    )
