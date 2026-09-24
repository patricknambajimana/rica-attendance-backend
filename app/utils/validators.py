import re

USERNAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,29}$")


def validate_password(password: str) -> str:
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters")
    if len(password.encode()) > 72:
        raise ValueError("Password is too long (72 bytes maximum)")
    if not any(c.isalpha() for c in password) or not any(c.isdigit() for c in password):
        raise ValueError("Password must contain both letters and numbers")
    return password


def normalize_username(username: str) -> str:
    username = username.strip().lower()
    if not USERNAME_RE.match(username):
        raise ValueError(
            "Username must be 3-30 characters (letters, numbers, dot, underscore, hyphen) "
            "and start with a letter or number"
        )
    return username
