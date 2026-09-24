from flask import Flask

from .config import Config
from .db import init_indexes


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.from_object(Config)
    if test_config:
        app.config.update(test_config)

    from .routes.admin import admin_bp
    from .routes.api import api_bp
    from .routes.public import public_bp

    app.register_blueprint(public_bp)
    app.register_blueprint(api_bp, url_prefix="/api")
    app.register_blueprint(admin_bp, url_prefix="/admin")
    @app.context_processor
    def inject_globals():
        return {"app_name": "Thành Nhân Badminton"}

    if not app.config.get("TESTING"):
        with app.app_context():
            try:
                init_indexes()
            except Exception as exc:
                app.logger.warning("Chưa thể kết nối MongoDB khi khởi động: %s", exc)

    return app
