from flask import jsonify
from pydantic import ValidationError


class AppError(Exception):
    """Raise this anywhere in services/decorators for a clean JSON error
    response, instead of returning jsonify(...) tuples by hand."""

    def __init__(self, message: str, status_code: int = 400, payload: dict | None = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.payload = payload or {}


def register_error_handlers(app):
    @app.errorhandler(AppError)
    def handle_app_error(err: AppError):
        body = {"error": err.message}
        body.update(err.payload)
        return jsonify(body), err.status_code

    @app.errorhandler(ValidationError)
    def handle_validation_error(err: ValidationError):
        return jsonify(error=err.errors(include_url=False, include_context=False)), 400

    @app.errorhandler(404)
    def handle_not_found(err):
        return jsonify(error="Not found"), 404

    @app.errorhandler(405)
    def handle_method_not_allowed(err):
        return jsonify(error="Method not allowed"), 405

    @app.errorhandler(500)
    def handle_internal_error(err):
        app.logger.exception(err)
        return jsonify(error="Internal server error"), 500
