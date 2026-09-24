from flask import Flask, request, url_for

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
        # Các mạng xã hội cần URL ảnh tuyệt đối. Render chạy sau HTTPS proxy,
        # vì vậy ép HTTPS cho mọi hostname không phải môi trường local.
        local_host = request.host.split(":", 1)[0] in {"127.0.0.1", "localhost"}
        scheme = request.scheme if local_host else "https"
        page_path = request.full_path.rstrip("?")
        return {
            "app_name": "Thành Nhân Badminton",
            "share_image_url": url_for(
                "public.brand_logo", _external=True, _scheme=scheme
            ),
            "share_page_url": f"{scheme}://{request.host}{page_path}",
        }

    if not app.config.get("TESTING"):
        with app.app_context():
            try:
                init_indexes()
            except Exception as exc:
                app.logger.warning("Chưa thể kết nối MongoDB khi khởi động: %s", exc)

    return app
