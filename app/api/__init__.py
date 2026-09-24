def register_blueprints(app):
    from .auth import bp as auth_bp
    from .health import bp as health_bp
    from .users import bp as users_bp

    app.register_blueprint(health_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(users_bp)
