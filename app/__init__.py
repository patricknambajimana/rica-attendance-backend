from flask import Flask
from flasgger import Swagger
from flask_cors import CORS
from dotenv import load_dotenv

from .utils import jwt_handlers
from .config import Config
from .extensions import db, jwt
from .utils.errors import register_error_handlers

load_dotenv()


def create_app() -> Flask:
    app = Flask(__name__)
    app.config.from_object(Config)

    swagger_template = {
    "securityDefinitions": {
        "Bearer": {
            "type": "apiKey",
            "name": "Authorization",
            "in": "header",
            "description": "Enter: Bearer <your JWT access token>",
        }
    },
    "security": [{"Bearer": []}],
}
    # --- CORS: allow only the origins listed in CORS_ORIGINS ---
    # --- CORS Configuration ---
    # Parse origins safely from Config or environment
    # ✅ SAFE — explicit origins always
    raw_origins = app.config.get("CORS_ORIGINS", "")

    if isinstance(raw_origins, str):
        origins = [o.strip() for o in raw_origins.split(",") if o.strip()]
    elif isinstance(raw_origins, list):
        origins = raw_origins
    else:
        origins = []

    # Fallback to a SAFE list, never "*"
    if not origins:
        origins = [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:3000",
        ]

    print("CORS allowed origins:", origins)   # debug

    CORS(
        app,
        resources={r"/*": {"origins": origins}},
        supports_credentials=True,
        allow_headers=["Content-Type", "Authorization"],
        expose_headers=["Authorization"],
        methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        max_age=3600,
    )
    # --- Database: one Prisma client, connected for the app's lifetime ---
    if not db.is_connected():
        db.connect()
    # --- JWT ---
    jwt.init_app(app)
    Swagger(app, template=swagger_template)
    register_error_handlers(app)
    # --- Routes ---
    from .api import register_blueprints
    register_blueprints(app)

    return app