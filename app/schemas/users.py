from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from ..utils.validators import normalize_username, role_str, validate_password

RoleName = Literal["ADMIN", "DIRECTOR", "HOD"]


class UserCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    username: str
    full_name: str = Field(min_length=2, max_length=100)
    temp_password: str
    role: RoleName
    department_id: Optional[str] = None

    @field_validator("email")
    @classmethod
    def _lower_email(cls, v: str) -> str:
        return v.lower()

    @field_validator("username")
    @classmethod
    def _check_username(cls, v: str) -> str:
        return normalize_username(v)

    @field_validator("temp_password")
    @classmethod
    def _check_password(cls, v: str) -> str:
        return validate_password(v)

    @model_validator(mode="after")
    def _hod_needs_department(self):
        if self.role == "HOD" and not self.department_id:
            raise ValueError("A Head of Department must have a department_id")
        return self


class UserUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: Optional[EmailStr] = None
    username: Optional[str] = None
    full_name: Optional[str] = Field(default=None, min_length=2, max_length=100)
    role: Optional[RoleName] = None
    department_id: Optional[str] = None
    is_active: Optional[bool] = None

    @field_validator("email")
    @classmethod
    def _lower_email(cls, v):
        return v.lower() if v else v

    @field_validator("username")
    @classmethod
    def _check_username(cls, v):
        return normalize_username(v) if v is not None else v


class ResetPasswordIn(BaseModel):
    new_password: str

    @field_validator("new_password")
    @classmethod
    def _check_password(cls, v: str) -> str:
        return validate_password(v)


def user_out(u) -> dict:
    return {
        "id": u.id,
        "email": u.email,
        "username": u.username,
        "full_name": u.fullName,
        "role": role_str(u.role),
        "department_id": u.departmentId,
        "is_active": u.isActive,
        "must_change_password": u.mustChangePassword,
        "last_login_at": u.lastLoginAt.isoformat() if u.lastLoginAt else None,
    }