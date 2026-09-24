import io
import base64
import json
import os
import re
from datetime import datetime
from pathlib import Path
from secrets import token_hex
from urllib.parse import urlparse

from flask import current_app
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload


SCOPES = ["https://www.googleapis.com/auth/drive.file"]
FOLDER_MIME_TYPE = "application/vnd.google-apps.folder"
ALLOWED_IMAGE_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/heic": ".heic",
    "image/heif": ".heif",
}
MAX_FILE_BYTES = 12 * 1024 * 1024
MAX_FILES_PER_UPLOAD = 6
TOKEN_DOCUMENT_ID = "google_drive_oauth"


class DriveNotConnected(RuntimeError):
    pass


class InvalidEvidenceFile(ValueError):
    pass


def _client_file():
    return Path(current_app.config["GOOGLE_OAUTH_CLIENT_FILE"]).expanduser().resolve()


def _token_file():
    return Path(current_app.config["GOOGLE_TOKEN_FILE"]).expanduser().resolve()


def _parse_client_json(raw):
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        try:
            decoded = base64.b64decode(raw).decode("utf-8")
            return json.loads(decoded)
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
            return None


def _client_config():
    raw_config = current_app.config.get("GOOGLE_OAUTH_CLIENT_JSON", "").strip()
    config = _parse_client_json(raw_config)
    if config:
        return config

    client_id = current_app.config.get("GOOGLE_OAUTH_CLIENT_ID", "").strip()
    client_secret = current_app.config.get("GOOGLE_OAUTH_CLIENT_SECRET", "").strip()
    if client_id and client_secret:
        return {
            "web": {
                "client_id": client_id,
                "project_id": current_app.config.get("GOOGLE_OAUTH_PROJECT_ID", "").strip(),
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
                "client_secret": client_secret,
                "redirect_uris": [current_app.config["GOOGLE_OAUTH_REDIRECT_URI"]],
            }
        }

    path = _client_file()
    if path.is_file():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
    return None


def client_file_exists():
    # Giữ tên hàm cũ để không làm thay đổi giao diện quản trị.
    return _client_config() is not None


def _mongo_token_data():
    try:
        from ..db import get_db

        document = get_db().app_settings.find_one({"_id": TOKEN_DOCUMENT_ID})
        return (document or {}).get("credentials")
    except Exception as exc:
        current_app.logger.warning("Không thể đọc token Google Drive từ MongoDB: %s", exc)
        return None


def _file_token_data():
    path = _token_file()
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _stored_token_data():
    return _mongo_token_data() or _file_token_data()


def drive_connected():
    return client_file_exists() and _stored_token_data() is not None


def _allow_local_http():
    redirect_uri = current_app.config["GOOGLE_OAUTH_REDIRECT_URI"]
    parsed = urlparse(redirect_uri)
    if parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost"}:
        os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")


def create_authorization_flow(state=None):
    client_config = _client_config()
    if not client_config:
        raise FileNotFoundError(
            "Chưa có cấu hình OAuth. Hãy khai báo GOOGLE_OAUTH_CLIENT_ID và "
            "GOOGLE_OAUTH_CLIENT_SECRET trên máy chủ."
        )
    _allow_local_http()
    flow = Flow.from_client_config(client_config, scopes=SCOPES, state=state)
    flow.redirect_uri = current_app.config["GOOGLE_OAUTH_REDIRECT_URI"]
    return flow


def save_credentials(credentials):
    data = json.loads(credentials.to_json())
    mongo_saved = False
    try:
        from ..db import get_db

        get_db().app_settings.update_one(
            {"_id": TOKEN_DOCUMENT_ID},
            {"$set": {"credentials": data, "updated_at": datetime.utcnow()}},
            upsert=True,
        )
        mongo_saved = True
    except Exception as exc:
        current_app.logger.warning("Không thể lưu token Google Drive vào MongoDB: %s", exc)

    file_saved = False
    try:
        path = _token_file()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")
        file_saved = True
    except OSError as exc:
        current_app.logger.warning("Không thể lưu bản sao token Google Drive ra file: %s", exc)

    if not mongo_saved and not file_saved:
        raise DriveNotConnected("Không thể lưu phiên kết nối Google Drive.")


def load_credentials():
    data = _stored_token_data()
    if not data:
        raise DriveNotConnected("Google Drive chưa được kết nối trong trang quản trị.")

    credentials = Credentials.from_authorized_user_info(data, SCOPES)
    if credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())
        save_credentials(credentials)
    if not credentials.valid:
        raise DriveNotConnected("Phiên Google Drive đã hết hạn. Hãy kết nối lại trong trang quản trị.")
    return credentials


def get_drive_service():
    return build("drive", "v3", credentials=load_credentials(), cache_discovery=False)


def _escape_query(value):
    return value.replace("\\", "\\\\").replace("'", "\\'")


def _find_folder(service, name, parent_id=None):
    clauses = [
        f"name = '{_escape_query(name)}'",
        f"mimeType = '{FOLDER_MIME_TYPE}'",
        "trashed = false",
    ]
    if parent_id:
        clauses.append(f"'{_escape_query(parent_id)}' in parents")
    response = service.files().list(
        q=" and ".join(clauses),
        spaces="drive",
        fields="files(id, name)",
        pageSize=1,
    ).execute()
    files = response.get("files", [])
    return files[0]["id"] if files else None


def _ensure_folder(service, name, parent_id=None):
    folder_id = _find_folder(service, name, parent_id)
    if folder_id:
        return folder_id
    metadata = {"name": name, "mimeType": FOLDER_MIME_TYPE}
    if parent_id:
        metadata["parents"] = [parent_id]
    folder = service.files().create(body=metadata, fields="id").execute()
    return folder["id"]


def ensure_month_folder(service, month):
    root_id = _ensure_folder(service, current_app.config["GOOGLE_DRIVE_FOLDER_NAME"])
    return _ensure_folder(service, month, root_id)


def _safe_filename(filename, mime_type):
    original = Path(filename or "minh-chung").name
    stem = re.sub(r"[^0-9A-Za-zÀ-ỹ_-]+", "-", Path(original).stem).strip("-_")
    stem = stem[:70] or "minh-chung"
    suffix = ALLOWED_IMAGE_TYPES[mime_type]
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"{timestamp}-{token_hex(3)}-{stem}{suffix}"


def validate_evidence_file(file_storage):
    mime_type = (file_storage.mimetype or "").lower()
    if mime_type not in ALLOWED_IMAGE_TYPES:
        raise InvalidEvidenceFile(
            f"{file_storage.filename or 'Tệp'} không phải ảnh JPG, PNG, WEBP, HEIC hoặc HEIF."
        )

    stream = file_storage.stream
    stream.seek(0, io.SEEK_END)
    size = stream.tell()
    stream.seek(0)
    if size <= 0:
        raise InvalidEvidenceFile(f"{file_storage.filename or 'Tệp'} đang rỗng.")
    if size > MAX_FILE_BYTES:
        raise InvalidEvidenceFile(
            f"{file_storage.filename or 'Tệp'} vượt quá giới hạn 12 MB."
        )
    return mime_type, size


def upload_evidence_files(files, month):
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", month or ""):
        raise InvalidEvidenceFile("Tháng giải đấu không hợp lệ.")
    if not files:
        raise InvalidEvidenceFile("Hãy chọn ít nhất một ảnh minh chứng.")
    if len(files) > MAX_FILES_PER_UPLOAD:
        raise InvalidEvidenceFile(f"Mỗi lần chỉ được tải tối đa {MAX_FILES_PER_UPLOAD} ảnh.")

    validated = [(item, *validate_evidence_file(item)) for item in files]
    service = get_drive_service()
    folder_id = ensure_month_folder(service, month)
    uploaded = []

    for item, mime_type, size in validated:
        media = MediaIoBaseUpload(
            item.stream, mimetype=mime_type, chunksize=1024 * 1024, resumable=True
        )
        result = service.files().create(
            body={
                "name": _safe_filename(item.filename, mime_type),
                "parents": [folder_id],
                "description": f"Minh chứng giải cầu lông Thành Nhân - tháng {month}",
            },
            media_body=media,
            fields="id,name,webViewLink,thumbnailLink",
        ).execute()
        uploaded.append({
            "id": result["id"],
            "name": result["name"],
            "url": result.get("webViewLink") or f"https://drive.google.com/file/d/{result['id']}/view",
            "thumbnail_url": result.get("thumbnailLink"),
            "size": size,
        })
    return uploaded


def token_summary():
    if not drive_connected():
        return {"connected": False, "client_ready": client_file_exists()}
    try:
        data = _stored_token_data() or {}
        return {
            "connected": True,
            "client_ready": True,
            "account_hint": data.get("client_id", "")[-12:],
        }
    except (OSError, ValueError):
        return {"connected": False, "client_ready": client_file_exists()}
