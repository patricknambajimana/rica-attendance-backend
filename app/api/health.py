from flask import Blueprint, jsonify

from ..extensions import db

bp = Blueprint("health", __name__)


@bp.get("/health")
def health():
    db_ok = db.is_connected()
    return jsonify(status="ok" if db_ok else "degraded", database="connected" if db_ok else "disconnected")
