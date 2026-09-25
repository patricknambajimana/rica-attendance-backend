"""
flask_jwt_extended callbacks. Imported (for its side effects) once from
create_app(), so these get registered on the shared `jwt` instance.
"""
from flask import jsonify

from ..extensions import db, jwt


@jwt.token_in_blocklist_loader
def check_if_token_revoked(jwt_header, jwt_payload) -> bool:
    jti = jwt_payload["jti"]
    return db.tokenblocklist.find_unique(where={"jti": jti}) is not None


@jwt.expired_token_loader
def expired_token_callback(jwt_header, jwt_payload):
    return jsonify(error="Token has expired"), 401


@jwt.invalid_token_loader
def invalid_token_callback(reason):
    return jsonify(error="Invalid token", detail=reason), 401


@jwt.unauthorized_loader
def missing_token_callback(reason):
    return jsonify(error="Authorization token required", detail=reason), 401


@jwt.revoked_token_loader
def revoked_token_callback(jwt_header, jwt_payload):
    return jsonify(error="Token has been revoked"), 401
