from typing import Literal, Optional
from flask import Blueprint, request, jsonify
from flask_jwt_extended import create_access_token
from pydantic import BaseModel, EmailStr, Field, ValidationError, model_validator
from ..db import db
from ..security import hash_password, check_password, roles_required

bp = Blueprint("auth", __name__, url_prefix="/api")

class UserCreate(BaseModel):
    email: EmailStr
    full_name: str
    password: str = Field(min_length=8)
    role: Literal["ADMIN", "DIRECTOR", "HOD"]
    department_id: Optional[str] = None

    @model_validator(mode="after")
    def hod_needs_department(self):
        if self.role == "HOD" and not self.department_id:
            raise ValueError("HOD must have a department_id")
        return self

@bp.post("/auth/login")
def login():
    data = request.get_json(silent=True) or {}
    user = db.user.find_unique(where={"email": data.get("email", "").lower()})
    if not user or not user.isActive or not check_password(data.get("password", ""), user.passwordHash):
        return jsonify(error="Invalid credentials"), 401
    token = create_access_token(
        identity=user.id,
        additional_claims={"role": user.role.value, "department_id": user.departmentId},
    )
    return jsonify(access_token=token, role=user.role.value, full_name=user.fullName)

@bp.post("/users")
@roles_required("ADMIN")
def create_user():
    try:
        body = UserCreate(**(request.get_json(silent=True) or {}))
    except ValidationError as e:
        return jsonify(error=e.errors(include_url=False, include_context=False)), 400

    if db.user.find_unique(where={"email": body.email.lower()}):
        return jsonify(error="Email already exists"), 409

    user = db.user.create(data={
        "email": body.email.lower(),
        "fullName": body.full_name,
        "passwordHash": hash_password(body.password),
        "role": body.role,
        **({"departmentId": body.department_id} if body.department_id else {}),
    })
    return jsonify(id=user.id, email=user.email, role=user.role.value), 201