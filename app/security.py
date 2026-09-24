from functools import wraps
import bcrypt
from flask import jsonify
from flask_jwt_extended import verify_jwt_in_request, get_jwt

def hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()

def check_password(pw: str, hashed: str) -> bool:
    return bcrypt.checkpw(pw.encode(), hashed.encode())

def roles_required(*roles):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            verify_jwt_in_request()
            if get_jwt().get("role") not in roles:
                return jsonify(error="Forbidden"), 403
            return fn(*args, **kwargs)
        return wrapper
    return decorator