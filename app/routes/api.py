from datetime import datetime
from secrets import token_hex

from flask import Blueprint, current_app, jsonify, request
from googleapiclient.errors import HttpError

from ..db import get_db
from ..services.ranking import calculate_awards, calculate_contributors, calculate_rankings, summarize
from ..services.seasons import current_month, normalize_month
from ..services.validation import identity, validate_match_payload
from ..services.google_drive import (
    DriveNotConnected,
    InvalidEvidenceFile,
    upload_evidence_files,
)


api_bp = Blueprint("api", __name__)


@api_bp.post("/evidence")
def upload_evidence():
    files = [item for item in request.files.getlist("files") if item and item.filename]
    try:
        uploaded = upload_evidence_files(files, request.form.get("month", ""))
        return jsonify({"ok": True, "files": uploaded}), 201
    except (InvalidEvidenceFile, DriveNotConnected) as exc:
        return jsonify({"ok": False, "message": str(exc)}), 422
    except HttpError as exc:
        current_app.logger.exception("Google Drive API error: %s", exc)
        return jsonify({
            "ok": False,
            "message": "Google Drive từ chối tải ảnh. Ban Tổ chức cần kết nối lại Drive.",
        }), 502
    except Exception as exc:
        current_app.logger.exception("Evidence upload failed: %s", exc)
        return jsonify({
            "ok": False,
            "message": "Không thể tải ảnh lên Google Drive. Vui lòng thử lại.",
        }), 500


@api_bp.get("/health")
def health():
    try:
        db = get_db()
        db.command("ping")
        return jsonify({
            "ok": True,
            "database": db.name,
            "message": "MongoDB đã kết nối.",
        })
    except Exception as exc:
        current_app.logger.error("MongoDB health check failed: %s", exc)
        return jsonify({
            "ok": False,
            "database": current_app.config["MONGO_DB_NAME"],
            "message": "Không kết nối được MongoDB Atlas. Kiểm tra mạng và Atlas Network Access.",
            "error_type": type(exc).__name__,
        }), 503


def serialize_match(item):
    item = dict(item)
    item["id"] = str(item.pop("_id", ""))
    for key in ("submitted_at", "updated_at", "approved_at"):
        if item.get(key):
            item[key] = item[key].isoformat()
    return item


@api_bp.post("/matches")
def create_match():
    payload = request.get_json(silent=True) or request.form.to_dict()
    cleaned, errors = validate_match_payload(payload)
    if errors:
        return jsonify({"ok": False, "errors": errors}), 422

    db = get_db()
    season = db.seasons.find_one({"month": cleaned["month"]})
    if season and season.get("locked"):
        return jsonify({"ok": False, "message": "Tháng này đã khóa nhận kết quả."}), 423

    if cleaned["stage"] == "group":
        duplicate_candidates = db.matches.find({
            "month": cleaned["month"], "stage": "group", "status": {"$in": ["pending", "approved"]}
        })
        target = {identity(cleaned["player_a"]), identity(cleaned["player_b"])}
        for item in duplicate_candidates:
            if {identity(item["player_a"]), identity(item["player_b"])} == target:
                return jsonify({"ok": False, "errors": {"players": "Cặp vận động viên này đã có bản ghi vòng bảng trong tháng."}}), 409

    now = datetime.utcnow()
    cleaned.update({
        "match_code": f"TN-{cleaned['month'].replace('-', '')}-{token_hex(3).upper()}",
        "status": "pending",
        "submitted_at": now,
        "updated_at": now,
        "admin_note": "",
    })
    result = db.matches.insert_one(cleaned)
    return jsonify({"ok": True, "id": str(result.inserted_id), "match_code": cleaned["match_code"]}), 201


@api_bp.get("/results")
def get_results():
    month = normalize_month(request.args.get("month"), current_month())
    db = get_db()
    matches = list(db.matches.find({"month": month}).sort("submitted_at", 1))
    rankings = calculate_rankings(matches)
    contributors = calculate_contributors(matches)
    season = db.seasons.find_one({"month": month}) or {"locked": False}
    return jsonify({
        "month": month,
        "summary": summarize(matches, rankings),
        "rankings": rankings,
        "contributors": contributors,
        "awards": calculate_awards(
            matches, rankings, contributors, locked=season.get("locked", False),
            decisions=season.get("award_decisions", {}),
        ),
        "matches": [serialize_match(m) for m in matches if m.get("status") == "approved"],
    })
