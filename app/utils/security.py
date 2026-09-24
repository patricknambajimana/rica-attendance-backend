import bcrypt


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except ValueError:  # e.g. password longer than bcrypt's 72-byte limit
        return False


_DUMMY_HASH = hash_password("dummy-password-1")


def burn_password_check(password: str) -> None:
    """Spend the same time as a real check when the account does not exist,
    so response time does not reveal which usernames/emails are registered."""
    bcrypt.checkpw(password.encode()[:72], _DUMMY_HASH.encode())
