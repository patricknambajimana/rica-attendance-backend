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
    CORS(app, origins=app.config["CORS_ORIGINS"] or "*", supports_credentials=True)
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