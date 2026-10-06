from ..extensions import db
from ..schemas.users import ResetPasswordIn, UserCreate, UserUpdate
from ..utils.audit import log_action
from ..utils.errors import AppError
from ..utils.security import hash_password
from ..utils.validators import role_str


def _ensure_unique(email: str | None, username: str | None, exclude_id: str | None = None) -> None:
    if email:
        other = db.user.find_unique(where={"email": email})
        if other and other.id != exclude_id:
            raise AppError("Email is already in use", 409)
    if username:
        other = db.user.find_unique(where={"username": username})
        if other and other.id != exclude_id:
            raise AppError("Username is already taken", 409)


def _ensure_department(department_id: str) -> None:
    if db.department.find_unique(where={"id": department_id}) is None:
        raise AppError("Department not found", 404)


def get_user(user_id: str):
    user = db.user.find_unique(where={"id": user_id})
    if user is None:
        raise AppError("User not found", 404)
    return user


def create_user(body: UserCreate):
    _ensure_unique(body.email, body.username)
    department_id = body.department_id if body.role == "HOD" else None
    if department_id:
        _ensure_department(department_id)

    data = {
        "email": body.email,
        "username": body.username,
        "fullName": body.full_name.strip(),
        "passwordHash": hash_password(body.temp_password),
        "role": body.role,
        "mustChangePassword": True,
    }
    if department_id:
        data["departmentId"] = department_id
    user = db.user.create(data=data)
    log_action("MANAGE_USERS", entity_type="User", entity_id=user.id, delta={"created": user.email, "role": body.role})
    return user


def list_users(role: str | None, department_id: str | None, is_active: str | None):
    where = {}
    if role:
        where["role"] = role.upper()
    if department_id:
        where["departmentId"] = department_id
    if is_active in ("true", "false"):
        where["isActive"] = is_active == "true"
    return db.user.find_many(where=where, order={"createdAt": "desc"})


def update_user(user_id: str, body: UserUpdate, acting_user):
    user = get_user(user_id)
    sent = body.model_fields_set

    email = body.email if "email" in sent and body.email else None
    username = body.username if "username" in sent and body.username else None
    _ensure_unique(email, username, exclude_id=user.id)

    new_role = body.role if "role" in sent and body.role else role_str(user.role)
    new_active = body.is_active if "is_active" in sent and body.is_active is not None else user.isActive
    new_department = body.department_id if "department_id" in sent else user.departmentId

    if new_role != "HOD":
        new_department = None  # Admin and Director are global
    elif not new_department:
        raise AppError("A Head of Department must have a department_id", 400)
    if new_department:
        _ensure_department(new_department)

    if user.id == acting_user.id and (new_role != "ADMIN" or not new_active):
        raise AppError("You cannot demote or deactivate your own account", 400)

    data = {"role": new_role, "isActive": new_active, "departmentId": new_department}
    if email:
        data["email"] = email
    if username:
        data["username"] = username
    if "full_name" in sent and body.full_name:
        data["fullName"] = body.full_name.strip()
    return db.user.update(where={"id": user.id}, data=data)


def delete_user(user_id: str, acting_user):
    user = db.user.find_unique(
        where={"id": user_id},
        include={
            "passwordResetTokens": True,
            "attendanceBatches": True,
            "resolvedAnomalies": True,
            "verifiedRaw": True,
            "verifiedFinal": True,
            "leavesCreated": True,
            "shiftsCreated": True,
            "holidaysCreated": True,
        },
    )
    if user is None:
        raise AppError("User not found", 404)
    if user.id == acting_user.id:
        raise AppError("You cannot delete your own account", 400)

    linked_records = {
        "password reset token(s)": user.passwordResetTokens,
        "attendance batch(es)": user.attendanceBatches,
        "resolved anomaly record(s)": user.resolvedAnomalies,
        "verified attendance record(s)": [*user.verifiedRaw, *user.verifiedFinal],
        "leave record(s)": user.leavesCreated,
        "shift record(s)": user.shiftsCreated,
        "holiday record(s)": user.holidaysCreated,
    }
    blocking_records = [label for label, records in linked_records.items() if records]
    if blocking_records:
        raise AppError(
            "User cannot be deleted because it has linked "
            + ", ".join(blocking_records)
            + ". Deactivate the account instead.",
            409,
        )

    log_action(
        "MANAGE_USERS",
        user_id=acting_user.id,
        entity_type="User",
        entity_id=user.id,
        delta={"deleted": user.email},
    )
    db.user.delete(where={"id": user.id})
    return {"message": "User deleted", "id": user.id}


def reset_password(user_id: str, body: ResetPasswordIn) -> None:
    user = get_user(user_id)
    db.user.update(
        where={"id": user.id},
        data={
            "passwordHash": hash_password(body.new_password),
            "mustChangePassword": True,
            "failedLogins": 0,
            "lockedUntil": None,
        },
    )