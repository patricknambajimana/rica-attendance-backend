from flask import jsonify
from pydantic import ValidationError
from werkzeug.exceptions import HTTPException


class AppError(Exception):
    """Raised anywhere in the service layer; turned into a JSON response."""

    def __init__(self, message: str, status: int = 400, details=None):
        super().__init__(message)
        self.message = message
        self.status = status
        self.details = details


def _format_validation_errors(exc: ValidationError) -> list[dict]:
    return [
        {
            "field": ".".join(str(p) for p in err["loc"]),
            "message": err["msg"].removeprefix("Value error, "),
        }
        for err in exc.errors()
    ]


def register_error_handlers(app):
    @app.errorhandler(AppError)
    def handle_app_error(e: AppError):
        body = {"error": e.message}
        if e.details:
            body["details"] = e.details
        return jsonify(body), e.status

    @app.errorhandler(ValidationError)
    def handle_validation_error(e: ValidationError):
        return jsonify(error="Validation failed", details=_format_validation_errors(e)), 400

    @app.errorhandler(HTTPException)
    def handle_http_error(e: HTTPException):
        return jsonify(error=e.description or e.name), e.code

    @app.errorhandler(Exception)
    def handle_unexpected(e: Exception):
        app.logger.exception(e)
        return jsonify(error="Internal server error"), 500
