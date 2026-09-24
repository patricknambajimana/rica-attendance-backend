import jwt
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
from flask import current_app

def hash_password(password: str) -> str:
    """Hashes plain-text passwords securely using Werkzeug (PBKDF2 / Scrypt)."""
    return generate_password_hash(password)

def verify_password(password: str, password_hash: str) -> bool:
    """Verifies a plain-text password against the stored hash."""
    return check_password_hash(password_hash, password)

def generate_token(user_id: str, role: str) -> str:
    """Generates a JWT token containing user identity and role."""
    payload = {
        'sub': user_id,
        'role': role,
        'iat': datetime.utcnow(),
        'exp': datetime.utcnow() + timedelta(hours=8)
    }
    return jwt.encode(payload, current_app.config['SECRET_KEY'], algorithm='HS256')