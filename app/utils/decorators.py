from functools import wraps

from flask import g
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request

from ..extensions import db
from .errors import AppError
from .validators import role_str


def auth_required(*roles: str, allow_pending: bool = False):
    """
    Usage:
      @auth_required()                 -> any authenticated, active, non-pending user
      @auth_required(allow_pending=True) -> also allow users with mustChangePassword=True
      @auth_required("ADMIN")          -> only ADMIN role
      @auth_required("ADMIN", "DIRECTOR")
    """

    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            verify_jwt_in_request()
            user_id = get_jwt_identity()
            user = db.user.find_unique(where={"id": user_id})

            if user is None or not user.isActive:
                raise AppError("Account not found or disabled", 401)

            if user.mustChangePassword and not allow_pending:
                raise AppError("Password change required before continuing", 403)

            if roles and role_str(user.role) not in roles:
                raise AppError("Insufficient permissions", 403)

            g.user = user
            return fn(*args, **kwargs)

        return wrapper

    return decorator