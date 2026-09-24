from flask import jsonify

from ..extensions import db


def register_jwt_handlers(jwt):
    @jwt.token_in_blocklist_loader
    def is_token_revoked(jwt_header, jwt_payload):
        return db.tokenblocklist.find_unique(where={"jti": jwt_payload["jti"]}) is not None

    @jwt.revoked_token_loader
    def revoked(jwt_header, jwt_payload):
        return jsonify(error="Token has been revoked"), 401

    @jwt.expired_token_loader
    def expired(jwt_header, jwt_payload):
        return jsonify(error="Token has expired"), 401

    @jwt.invalid_token_loader
    def invalid(reason):
        return jsonify(error="Invalid token"), 401

    @jwt.unauthorized_loader
    def missing(reason):
        return jsonify(error="Authorization token required"), 401
