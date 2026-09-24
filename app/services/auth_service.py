from datetime import datetime, timedelta, timezone

from flask import current_app
from flask_jwt_extended import create_access_token, create_refresh_token, decode_token

from ..extensions import db
from ..schemas.users import user_out
from ..utils.errors import AppError
from ..utils.security import burn_password_check, hash_password, verify_password


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt):
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def find_user_by_identifier(identifier: str):
    """Look a user up by email (contains '@') or by username."""
    ident = identifier.strip().lower()
    where = {"email": ident} if "@" in ident else {"username": ident}
    return db.user.find_unique(where=where)


def _access_token(user) -> str:
    return create_access_token(
        identity=user.id,
        additional_claims={"role": user.role.value, "department_id": user.departmentId},
    )


def revoke_token(jti: str, exp: int) -> None:
    if db.tokenblocklist.find_unique(where={"jti": jti}) is None:
        db.tokenblocklist.create(
            data={"jti": jti, "expiresAt": datetime.fromtimestamp(exp, tz=timezone.utc)}
        )


def _register_failed_login(user, now: datetime) -> None:
    cfg = current_app.config
    fails = user.failedLogins + 1
    if fails >= cfg["MAX_FAILED_LOGINS"]:
        data = {
            "failedLogins": 0,
            "lockedUntil": now + timedelta(minutes=cfg["LOCKOUT_MINUTES"]),
        }
    else:
        data = {"failedLogins": fails}
    db.user.update(where={"id": user.id}, data=data)


def login(identifier: str, password: str) -> dict:
    now = _now()
    user = find_user_by_identifier(identifier)

    if user is None:
        burn_password_check(password)
        raise AppError("Invalid credentials", 401)

    locked_until = _aware(user.lockedUntil)
    if locked_until and locked_until > now:
        raise AppError("Account temporarily locked. Try again later.", 423)

    if not verify_password(password, user.passwordHash) or not user.isActive:
        _register_failed_login(user, now)
        raise AppError("Invalid credentials", 401)

    user = db.user.update(
        where={"id": user.id},
        data={"failedLogins": 0, "lockedUntil": None, "lastLoginAt": now},
    )
    return {
        "access_token": _access_token(user),
        "refresh_token": create_refresh_token(identity=user.id),
        "must_change_password": user.mustChangePassword,
        "user": user_out(user),
    }


def refresh(user_id: str) -> dict:
    user = db.user.find_unique(where={"id": user_id})
    if user is None or not user.isActive:
        raise AppError("Account not found or disabled", 401)
    return {"access_token": _access_token(user)}


def logout(access_claims: dict, user_id: str, refresh_token: str | None = None) -> None:
    revoke_token(access_claims["jti"], access_claims["exp"])
    if refresh_token:
        try:
            decoded = decode_token(refresh_token)
        except Exception:
            return  # already expired/invalid: nothing to revoke
        if decoded.get("type") == "refresh" and decoded.get("sub") == user_id:
            revoke_token(decoded["jti"], decoded["exp"])


def change_password(user, access_claims: dict, current_password: str, new_password: str) -> None:
    if not verify_password(current_password, user.passwordHash):
        raise AppError("Current password is incorrect", 400)
    if current_password == new_password:
        raise AppError("New password must be different from the current one", 400)
    db.user.update(
        where={"id": user.id},
        data={"passwordHash": hash_password(new_password), "mustChangePassword": False},
    )
    revoke_token(access_claims["jti"], access_claims["exp"])
