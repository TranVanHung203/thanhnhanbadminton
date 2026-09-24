from flask import current_app
from pymongo import ASCENDING, DESCENDING, MongoClient


def get_client():
    # MongoClient là thread-safe và tự quản lý connection pool. Giữ một client
    # cho toàn bộ tiến trình Flask để tránh phải DNS/TLS lại ở mỗi request.
    client = current_app.extensions.get("mongo_client")
    if client is None:
        client = MongoClient(
            current_app.config["MONGO_URI"],
            serverSelectionTimeoutMS=15000,
            connectTimeoutMS=10000,
            socketTimeoutMS=20000,
            retryReads=True,
            retryWrites=True,
            appname="thanh-nhan-badminton",
        )
        current_app.extensions["mongo_client"] = client
    return client


def get_db():
    # Chủ động chọn `thanh_nhan`; tuyệt đối không dùng get_default_database().
    return get_client()[current_app.config["MONGO_DB_NAME"]]


def init_indexes():
    db = get_db()
    db.command("ping")
    db.matches.create_index([("month", ASCENDING), ("status", ASCENDING), ("submitted_at", ASCENDING)])
    db.matches.create_index([("match_code", ASCENDING)], unique=True, sparse=True)
    db.seasons.create_index([("month", ASCENDING)], unique=True)
    db.audit_logs.create_index([("created_at", DESCENDING)])
