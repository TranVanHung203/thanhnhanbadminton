import base64
import json

from flask import Flask

from app.services.google_drive import _client_config


def make_app(**config):
    app = Flask(__name__)
    app.config.update(
        GOOGLE_OAUTH_CLIENT_FILE="missing-oauth-file.json",
        GOOGLE_OAUTH_CLIENT_JSON="",
        GOOGLE_OAUTH_CLIENT_ID="",
        GOOGLE_OAUTH_CLIENT_SECRET="",
        GOOGLE_OAUTH_PROJECT_ID="",
        GOOGLE_OAUTH_REDIRECT_URI="https://example.onrender.com/admin/google/callback",
    )
    app.config.update(config)
    return app


def test_client_config_can_be_built_from_render_environment_values():
    app = make_app(
        GOOGLE_OAUTH_CLIENT_ID="client-id.apps.googleusercontent.com",
        GOOGLE_OAUTH_CLIENT_SECRET="client-secret",
        GOOGLE_OAUTH_PROJECT_ID="thanh-nhan",
    )
    with app.app_context():
        config = _client_config()

    assert config["web"]["client_id"] == "client-id.apps.googleusercontent.com"
    assert config["web"]["client_secret"] == "client-secret"
    assert config["web"]["redirect_uris"] == [
        "https://example.onrender.com/admin/google/callback"
    ]


def test_client_config_accepts_base64_json():
    payload = {"web": {"client_id": "encoded-id", "client_secret": "encoded-secret"}}
    encoded = base64.b64encode(json.dumps(payload).encode()).decode()
    app = make_app(GOOGLE_OAUTH_CLIENT_JSON=encoded)

    with app.app_context():
        assert _client_config() == payload
