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
    raw_origins = app.config.get("CORS_ORIGINS")
    if isinstance(raw_origins, str) and raw_origins.strip():
        # Handles comma-separated string like "http://localhost:5173,https://yourdomain.com"
        origins = [o.strip() for o in raw_origins.split(",") if o.strip()]
    elif isinstance(raw_origins, list) and raw_origins:
        origins = raw_origins
    else:
        # Fallback to allow all origins if CORS_ORIGINS is not set or empty
        origins = "*"

    # Apply CORS explicitly to /api/* endpoints including preflight OPTIONS requests
    CORS(
        app,
        resources={r"/api/*": {"origins": origins}},
        supports_credentials=True,
        allow_headers=["Content-Type", "Authorization", "Access-Control-Allow-Credentials"],
        methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
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