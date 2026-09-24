# app/extensions.py
from flasgger import Swagger
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from prisma import Prisma

db = Prisma()
jwt = JWTManager()
cors = CORS()

swagger = Swagger(
    template={
        "swagger": "2.0",
        "info": {"title": "RICA Attendance API", "version": "0.1.0"},
        "securityDefinitions": {
            "Bearer": {
                "type": "apiKey",
                "name": "Authorization",
                "in": "header",
                "description": "Format: Bearer <access_token>",
            }
        },
    }
)