from .errors import AppError
from .validators import role_str


def scoped_department_id(user, requested_department_id: str | None = None) -> str | None:
    """HOD is locked to their own department; Admin/Director may filter or see all."""
    role = role_str(user.role)
    if role == "HOD":
        if not user.departmentId:
            raise AppError("Head of Department account has no department assigned", 403)
        if requested_department_id and requested_department_id != user.departmentId:
            raise AppError("You can only access your own department", 403)
        return user.departmentId
    return requested_department_id or None
