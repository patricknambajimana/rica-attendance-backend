from flask import Blueprint, g, jsonify, request
from flask_jwt_extended import get_jwt, get_jwt_identity, jwt_required

from ..schemas.auth import ChangePasswordIn, LoginIn
from ..schemas.users import user_out
from ..services import auth_service
from ..utils.decorators import auth_required

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")


@auth_bp.post("/login")
def login():
    """Log in with email OR username
    ---
    tags: [Auth]
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required: [identifier, password]
          properties:
            identifier: {type: string, example: admin}
            password: {type: string}
    responses:
      200: {description: Access and refresh tokens}
      401: {description: Invalid credentials}
      423: {description: Account temporarily locked}
    """
    body = LoginIn.model_validate(request.get_json(silent=True) or {})
    return jsonify(auth_service.login(body.identifier, body.password))


@auth_bp.post("/refresh")
@jwt_required(refresh=True)
def refresh():
    """Get a new access token using a refresh token
    ---
    tags: [Auth]
    security: [{Bearer: []}]
    responses:
      200: {description: New access token}
    """
    return jsonify(auth_service.refresh(get_jwt_identity()))


@auth_bp.get("/me")
@auth_required(allow_pending=True)
def me():
    """Current user
    ---
    tags: [Auth]
    security: [{Bearer: []}]
    responses:
      200: {description: The logged-in user}
    """
    return jsonify(user_out(g.user))


@auth_bp.post("/logout")
@auth_required(allow_pending=True)
def logout():
    """Log out (revokes the access token, and the refresh token if sent)
    ---
    tags: [Auth]
    security: [{Bearer: []}]
    parameters:
      - in: body
        name: body
        schema:
          type: object
          properties:
            refresh_token: {type: string}
    responses:
      200: {description: Logged out}
    """
    refresh_token = (request.get_json(silent=True) or {}).get("refresh_token")
    auth_service.logout(get_jwt(), g.user.id, refresh_token)
    return jsonify(message="Logged out")


@auth_bp.post("/change-password")
@auth_required(allow_pending=True)
def change_password():
    """Change own password (required after first login or an admin reset)
    ---
    tags: [Auth]
    security: [{Bearer: []}]
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required: [current_password, new_password]
          properties:
            current_password: {type: string}
            new_password: {type: string}
    responses:
      200: {description: Password changed; log in again}
    """
    body = ChangePasswordIn.model_validate(request.get_json(silent=True) or {})
    auth_service.change_password(g.user, get_jwt(), body.current_password, body.new_password)
    return jsonify(message="Password changed. Please log in again.")
