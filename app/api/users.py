from flask import Blueprint, g, jsonify, request

from ..schemas.users import ResetPasswordIn, UserCreate, UserUpdate, user_out
from ..services import user_service
from ..utils.decorators import auth_required

users_bp = Blueprint("users", __name__, url_prefix="/api/users")


@users_bp.post("")
@auth_required("ADMIN")
def create_user():
    """Create a user (Admin only)
    ---
    tags: [Users]
    security: [{Bearer: []}]
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required: [email, username, full_name, temp_password, role]
          properties:
            email: {type: string}
            username: {type: string}
            full_name: {type: string}
            temp_password: {type: string}
            role: {type: string, enum: [ADMIN, DIRECTOR, HOD]}
            department_id: {type: string, description: Required when role is HOD}
    responses:
      201: {description: User created; must change password at first login}
    """
    body = UserCreate.model_validate(request.get_json(silent=True) or {})
    return jsonify(user_out(user_service.create_user(body))), 201


@users_bp.get("")
@auth_required("ADMIN")
def list_users():
    """List users (Admin only)
    ---
    tags: [Users]
    security: [{Bearer: []}]
    parameters:
      - {in: query, name: role, type: string}
      - {in: query, name: department_id, type: string}
      - {in: query, name: is_active, type: string, enum: ["true", "false"]}
    responses:
      200: {description: List of users}
    """
    users = user_service.list_users(
        request.args.get("role"),
        request.args.get("department_id"),
        request.args.get("is_active"),
    )
    return jsonify([user_out(u) for u in users])


@users_bp.get("/<user_id>")
@auth_required("ADMIN")
def get_user(user_id):
    """Get one user (Admin only)
    ---
    tags: [Users]
    security: [{Bearer: []}]
    parameters:
      - {in: path, name: user_id, type: string, required: true}
    responses:
      200: {description: The user}
      404: {description: Not found}
    """
    return jsonify(user_out(user_service.get_user(user_id)))


@users_bp.patch("/<user_id>")
@auth_required("ADMIN")
def update_user(user_id):
    """Update a user: name, email, username, role, department, active status (Admin only)
    ---
    tags: [Users]
    security: [{Bearer: []}]
    parameters:
      - {in: path, name: user_id, type: string, required: true}
      - in: body
        name: body
        schema:
          type: object
          properties:
            email: {type: string}
            username: {type: string}
            full_name: {type: string}
            role: {type: string, enum: [ADMIN, DIRECTOR, HOD]}
            department_id: {type: string}
            is_active: {type: boolean}
    responses:
      200: {description: Updated user}
    """
    body = UserUpdate.model_validate(request.get_json(silent=True) or {})
    return jsonify(user_out(user_service.update_user(user_id, body, g.user)))


@users_bp.post("/<user_id>/reset-password")
@auth_required("ADMIN")
def reset_password(user_id):
    """Set a new temporary password; user must change it at next login (Admin only)
    ---
    tags: [Users]
    security: [{Bearer: []}]
    parameters:
      - {in: path, name: user_id, type: string, required: true}
      - in: body
        name: body
        required: true
        schema:
          type: object
          required: [new_password]
          properties:
            new_password: {type: string}
    responses:
      200: {description: Password reset}
    """
    body = ResetPasswordIn.model_validate(request.get_json(silent=True) or {})
    user_service.reset_password(user_id, body)
    return jsonify(message="Password reset. The user must change it at next login.")
