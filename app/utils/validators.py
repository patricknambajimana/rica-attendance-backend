import re

_USERNAME_RE = re.compile(r"[a-z0-9_.-]{3,32}")


def validate_password(password: str) -> str:
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters long")
    if not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        raise ValueError("Password must contain at least one letter and one number")
    return password


def role_str(role) -> str:
    """Prisma-client-py has returned enum fields as either an Enum instance
    (with .value) or a plain str, depending on version/config. Handle both."""
    return getattr(role, "value", role)


def normalize_username(username: str) -> str:
    normalized = username.strip().lower()
    if not _USERNAME_RE.fullmatch(normalized):
        raise ValueError(
            "Username must be 3-32 characters: lowercase letters, numbers, '.', '_' or '-'"
        )
    return normalized