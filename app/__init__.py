from flask import Flask
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from flasgger import Swagger

from .config import Config
from .db import db

jwt = JWTManager()

def create_app():
    app = Flask(__name__)

    app.config.from_object(Config)

    CORS(app)
    jwt.init_app(app)
    Swagger(app)

    try:
        db.connect()
        print("✅Prisma Connected")
    except Exception as e:
        print(f" Prisma Connection Error: {e}")

    @jwt.token_in_blocklist_loader
    def is_revoked(jwt_header, jwt_payload):
        token = db.tokenblocklist.find_unique(
            where={"jti": jwt_payload["jti"]}
        )
        return token is not None

    from app.api.auth import auth_bp
    from app.api.users import users_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(users_bp)

    return app