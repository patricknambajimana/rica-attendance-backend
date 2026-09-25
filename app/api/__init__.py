def register_blueprints(app):
    from .attendance import bp as attendance_bp
    from .audit import bp as audit_bp
    from .auth import auth_bp
    from .catalog import bp as catalog_bp
    from .health import bp as health_bp
    from .leaves import bp as leaves_bp
    from .reports import bp as reports_bp
    from .users import users_bp

    app.register_blueprint(health_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(users_bp)
    app.register_blueprint(attendance_bp)
    app.register_blueprint(leaves_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(catalog_bp)
    app.register_blueprint(audit_bp)
