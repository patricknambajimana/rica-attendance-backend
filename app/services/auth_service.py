import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from flask import current_app
from flask_jwt_extended import create_access_token, create_refresh_token, decode_token

from ..extensions import db
from ..schemas.users import user_out
from ..utils.audit import log_action
from ..utils.errors import AppError
from ..utils.security import burn_password_check, hash_password, verify_password
from ..utils.validators import role_str

RESET_TOKEN_BYTES = 32


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
        additional_claims={"role": role_str(user.role), "department_id": user.departmentId},
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
    log_action("LOGIN", user_id=user.id, entity_type="User", entity_id=user.id)
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
    log_action("LOGOUT", user_id=user_id, entity_type="User", entity_id=user_id)
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


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def request_password_reset(identifier: str) -> str | None:
    """
    Create a single-use reset token for the account if it exists and is
    active. Returns the raw token (only the caller sees this — only the
    hash is stored), or None if there's no matching active account.

    The route always replies with the same generic message either way, so
    this function's return value must never be reflected back to an
    unauthenticated caller except in local debug mode — it exists so you
    can email it, or (until email is wired up) read it from the server log.
    """
    user = find_user_by_identifier(identifier)
    if user is None or not user.isActive:
        return None

    raw_token = secrets.token_urlsafe(RESET_TOKEN_BYTES)
    ttl = current_app.config["PASSWORD_RESET_TTL_MINUTES"]
    db.passwordresettoken.create(
        data={
            "userId": user.id,
            "tokenHash": _hash_token(raw_token),
            "expiresAt": _now() + timedelta(minutes=ttl),
        }
    )

    # TODO: replace with real email delivery once SMTP/an email provider is
    # configured. Logging it keeps the feature usable in the meantime for an
    # internal admin who's locked out and has server/log access.
    current_app.logger.info(
        "Password reset requested for %s (username=%s). Token: %s (expires in %s min)",
        user.email, user.username, raw_token, ttl,
    )
    return raw_token


def reset_password_with_token(token: str, new_password: str) -> None:
    record = db.passwordresettoken.find_unique(where={"tokenHash": _hash_token(token)})
    now = _now()

    if (
        record is None
        or record.usedAt is not None
        or _aware(record.expiresAt) < now
    ):
        raise AppError("Invalid or expired reset token", 400)

    db.user.update(
        where={"id": record.userId},
        data={
            "passwordHash": hash_password(new_password),
            "mustChangePassword": False,
            "failedLogins": 0,
            "lockedUntil": None,
        },
    )
    db.passwordresettoken.update(where={"id": record.id}, data={"usedAt": now})