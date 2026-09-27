from flask import Blueprint, jsonify

from ..extensions import db

bp = Blueprint("health", __name__)


@bp.get("/health")
def health():
    """Liveness/readiness check, including database connectivity
    ---
    tags: [Health]
    responses:
      200:
        description: Service status
        schema:
          type: object
          properties:
            status: {type: string, enum: [ok, degraded]}
            database: {type: string, enum: [connected, disconnected]}
    """
    db_ok = db.is_connected()
    return jsonify(status="ok" if db_ok else "degraded", database="connected" if db_ok else "disconnected")