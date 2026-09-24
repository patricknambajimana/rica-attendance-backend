from functools import wraps

from flask import g
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request

from ..extensions import db
from .errors import AppError


def auth_required(*roles: str, allow_pending: bool = False):
    """Require a valid access token.

    - The user is re-loaded from the database on every request, so role changes
      and deactivation take effect immediately.
    - roles: if given, the user must have one of these roles.
    - allow_pending: let users who still must change their password through
      (only /me, /logout and /change-password use this).
    The user is available as flask.g.user.
    """

    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            verify_jwt_in_request()
            user = db.user.find_unique(where={"id": get_jwt_identity()})
            if user is None or not user.isActive:
                raise AppError("Account not found or disabled", 401)
            if roles and user.role.value not in roles:
                raise AppError("You do not have permission to do this", 403)
            if user.mustChangePassword and not allow_pending:
                raise AppError("You must change your password before continuing", 403)
            g.user = user
            return fn(*args, **kwargs)

        return wrapper

    return decorator
