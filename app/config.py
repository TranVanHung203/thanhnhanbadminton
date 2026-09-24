import os
from pathlib import Path

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "change-me")
    MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
    # Luôn chọn database này bằng client[DB_NAME], không dùng database trong URI.
    MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "thanh_nhan")
    ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "change-me")
    PORT = int(os.getenv("PORT", "5000"))
    DEBUG = os.getenv("FLASK_DEBUG", "0").lower() in {"1", "true", "yes", "on"}
    JSON_AS_ASCII = False
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024
    GOOGLE_OAUTH_CLIENT_FILE = os.getenv(
        "GOOGLE_OAUTH_CLIENT_FILE", str(ROOT / "google-oauth.json.json")
    )
    # Trên Render không commit file OAuth. Có thể truyền toàn bộ JSON hoặc
    # chỉ truyền client ID/client secret bằng biến môi trường.
    GOOGLE_OAUTH_CLIENT_JSON = os.getenv("GOOGLE_OAUTH_CLIENT_JSON", "")
    GOOGLE_OAUTH_CLIENT_ID = os.getenv("GOOGLE_OAUTH_CLIENT_ID", "")
    GOOGLE_OAUTH_CLIENT_SECRET = os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", "")
    GOOGLE_OAUTH_PROJECT_ID = os.getenv("GOOGLE_OAUTH_PROJECT_ID", "")
    GOOGLE_TOKEN_FILE = os.getenv(
        "GOOGLE_TOKEN_FILE", str(ROOT / ".artifacts" / "google-drive-token.json")
    )
    GOOGLE_OAUTH_REDIRECT_URI = os.getenv(
        "GOOGLE_OAUTH_REDIRECT_URI", "http://127.0.0.1:5000/admin/google/callback"
    )
    GOOGLE_DRIVE_FOLDER_NAME = os.getenv(
        "GOOGLE_DRIVE_FOLDER_NAME", "Thành Nhân - Minh chứng giải cầu lông"
    )
