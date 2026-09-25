import os
from datetime import timedelta


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "change-me-in-env")
    JSON_SORT_KEYS = False

    # --- JWT (names match your .env: ACCESS_TOKEN_MINUTES / REFRESH_TOKEN_DAYS) ---
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "change-me-too-in-env")
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(minutes=int(os.getenv("ACCESS_TOKEN_MINUTES", "30")))
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=int(os.getenv("REFRESH_TOKEN_DAYS", "7")))

    # --- Login lockout policy (not in your .env yet; these are safe defaults) ---
    MAX_FAILED_LOGINS = int(os.getenv("MAX_FAILED_LOGINS", "5"))
    LOCKOUT_MINUTES = int(os.getenv("LOCKOUT_MINUTES", "15"))

    # --- Forgot-password token lifetime ---
    PASSWORD_RESET_TTL_MINUTES = int(os.getenv("PASSWORD_RESET_TTL_MINUTES", "30"))

    # --- CORS: comma-separated list, e.g. "http://localhost:3000,https://app.rica.com" ---
    CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]