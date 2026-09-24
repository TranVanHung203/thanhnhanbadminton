from datetime import datetime
from functools import wraps
from secrets import choice

from bson import ObjectId
from flask import Blueprint, current_app, flash, jsonify, redirect, render_template, request, session, url_for

from ..db import get_db
from ..services.ranking import calculate_awards, calculate_contributors, calculate_rankings, summarize
from ..services.seasons import available_months, current_month, normalize_month
from ..services.validation import identity
from ..services.google_drive import (
    create_authorization_flow,
    save_credentials,
    token_summary,
)


admin_bp = Blueprint("admin", __name__)
DRAW_DECISION_KEYS = {
    "achievement_second", "achievement_third",
    "head_to_head", "active_star", "active_flower",
}


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("is_admin"):
            return redirect(url_for("admin.login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


def log_action(action, match=None, details=""):
    get_db().audit_logs.insert_one({
        "action": action,
        "match_code": match.get("match_code") if match else None,
        "details": details,
        "created_at": datetime.utcnow(),
    })


def locked_match_message(db, match):
    season = db.seasons.find_one({"month": match.get("month")})
    if season and season.get("locked"):
        return "Mùa giải đã khóa. Hãy mở lại tháng trước khi thay đổi bản ghi."
    return None


@admin_bp.route("/dang-nhap", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if request.form.get("password") == current_app.config["ADMIN_PASSWORD"]:
            session["is_admin"] = True
            return redirect(request.args.get("next") or url_for("admin.dashboard"))
        flash("Mật khẩu không đúng.", "error")
    return render_template("admin/login.html")


@admin_bp.post("/dang-xuat")
def logout():
    session.clear()
    return redirect(url_for("public.home"))


@admin_bp.route("/")
@admin_required
def dashboard():
    db = get_db()
    month = normalize_month(request.args.get("month"), current_month())
    status = request.args.get("status", "all")
    query = {"month": month}
    if status in {"pending", "approved", "rejected"}:
        query["status"] = status
    visible_matches = list(db.matches.find(query).sort("submitted_at", -1))
    all_matches = list(db.matches.find({"month": month}).sort("submitted_at", 1))
    rankings = calculate_rankings(all_matches)
    contributors = calculate_contributors(all_matches)
    months = available_months(db, month)
    season = db.seasons.find_one({"month": month}) or {"month": month, "locked": False}
    return render_template(
        "admin/dashboard.html", month=month, months=months, status=status,
        matches=visible_matches, rankings=rankings, stats=summarize(all_matches, rankings), season=season,
        drive=token_summary(),
        awards=calculate_awards(
            all_matches, rankings, contributors, locked=season.get("locked", False),
            decisions=season.get("award_decisions", {}),
        ),
    )


def award_snapshot(db, month):
    month = normalize_month(month, current_month())
    matches = list(db.matches.find({"month": month}).sort("submitted_at", 1))
    rankings = calculate_rankings(matches)
    contributors = calculate_contributors(matches)
    season = db.seasons.find_one({"month": month}) or {"month": month, "locked": False}
    awards = calculate_awards(
        matches, rankings, contributors,
        locked=season.get("locked", False),
        decisions=season.get("award_decisions", {}),
    )
    return season, matches, rankings, contributors, awards


@admin_bp.get("/boc-tham")
@admin_required
def draw_awards():
    db = get_db()
    month = normalize_month(request.args.get("month"), current_month())
    season, matches, rankings, contributors, awards = award_snapshot(db, month)
    return render_template(
        "admin/draw.html",
        month=month,
        season=season,
        awards=awards,
        history=list(reversed(season.get("award_draw_history", [])[-20:])),
    )


def _find_draw_task(awards, draw_key):
    if draw_key not in DRAW_DECISION_KEYS:
        return None
    return next((item for item in awards.get("draws", []) if item["key"] == draw_key), None)


def _save_draw_decision(db, month, season, task, winner, method):
    decisions = dict(season.get("award_decisions", {}))
    key = task["key"]
    if key.startswith("achievement_"):
        selected = list(decisions.get(key, []))
        if not any(identity(item) == identity(winner) for item in selected):
            selected.append(winner)
        decisions[key] = selected
    else:
        decisions[key] = winner

    history_item = {
        "draw_key": key,
        "title": task["title"],
        "winner": winner,
        "method": method,
        "created_at": datetime.utcnow(),
    }
    db.seasons.update_one(
        {"month": month},
        {
            "$set": {
                "month": month,
                "award_decisions": decisions,
                "updated_at": datetime.utcnow(),
            },
            "$push": {"award_draw_history": history_item},
        },
        upsert=True,
    )
    log_action("award_draw" if method == "wheel" else "award_manual", details=f"{month}: {key} -> {winner}")


@admin_bp.post("/boc-tham/quay")
@admin_required
def spin_award_draw():
    payload = request.get_json(silent=True) or {}
    month = normalize_month(payload.get("month"), current_month())
    draw_key = str(payload.get("draw_key", ""))
    db = get_db()
    season, _, _, _, awards = award_snapshot(db, month)
    task = _find_draw_task(awards, draw_key)
    if not task or not task.get("candidates"):
        return jsonify({"ok": False, "message": "Hạng mục này không còn cần bốc thăm."}), 409

    winner = choice(task["candidates"])["name"]
    _save_draw_decision(db, month, season, task, winner, "wheel")
    return jsonify({
        "ok": True,
        "winner": winner,
        "draw_key": draw_key,
        "title": task["title"],
        "candidate_names": [item["name"] for item in task["candidates"]],
    })


@admin_bp.post("/boc-tham/chon")
@admin_required
def choose_award_manually():
    month = normalize_month(request.form.get("month"), current_month())
    draw_key = str(request.form.get("draw_key", ""))
    requested_winner = str(request.form.get("winner", "")).strip()
    db = get_db()
    season, _, _, _, awards = award_snapshot(db, month)
    task = _find_draw_task(awards, draw_key)
    winner = next(
        (item["name"] for item in (task or {}).get("candidates", [])
         if identity(item["name"]) == identity(requested_winner)),
        None,
    )
    if not task or not winner:
        flash("Người được chọn không còn nằm trong danh sách cần phân định.", "error")
    else:
        _save_draw_decision(db, month, season, task, winner, "manual")
        flash(f"Đã xác định {winner} cho {task['award_title']}.", "success")
    return redirect(url_for("admin.draw_awards", month=month))


@admin_bp.post("/boc-tham/xoa")
@admin_required
def reset_award_draw():
    month = normalize_month(request.form.get("month"), current_month())
    draw_key = str(request.form.get("draw_key", ""))
    if draw_key not in DRAW_DECISION_KEYS:
        flash("Hạng mục phân định không hợp lệ.", "error")
        return redirect(url_for("admin.draw_awards", month=month))
    db = get_db()
    season = db.seasons.find_one({"month": month}) or {}
    decisions = dict(season.get("award_decisions", {}))
    decisions.pop(draw_key, None)
    db.seasons.update_one(
        {"month": month},
        {"$set": {"month": month, "award_decisions": decisions, "updated_at": datetime.utcnow()}},
        upsert=True,
    )
    log_action("award_draw_reset", details=f"{month}: {draw_key}")
    flash("Đã xóa kết quả phân định để thực hiện lại.", "success")
    return redirect(url_for("admin.draw_awards", month=month))


@admin_bp.get("/google/connect")
@admin_required
def google_connect():
    try:
        flow = create_authorization_flow()
        authorization_url, state = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent",
        )
        session["google_oauth_state"] = state
        return redirect(authorization_url)
    except Exception as exc:
        current_app.logger.exception("Không thể bắt đầu kết nối Google Drive: %s", exc)
        flash("Không thể mở trang kết nối Google Drive. Hãy kiểm tra file OAuth.", "error")
        return redirect(url_for("admin.dashboard"))


@admin_bp.get("/google/callback")
@admin_required
def google_callback():
    expected_state = session.pop("google_oauth_state", None)
    returned_state = request.args.get("state")
    if not expected_state or returned_state != expected_state:
        flash("Phiên kết nối Google Drive không hợp lệ hoặc đã hết hạn.", "error")
        return redirect(url_for("admin.dashboard"))

    if request.args.get("error"):
        flash("Bạn chưa cấp quyền Google Drive cho ứng dụng.", "error")
        return redirect(url_for("admin.dashboard"))

    try:
        flow = create_authorization_flow(state=expected_state)
        # Render kết thúc TLS ở reverse proxy nên request.url đôi khi bị Flask
        # nhận thành http://. Dùng URI HTTPS đã cấu hình để OAuth token exchange
        # luôn khớp tuyệt đối với redirect_uri đã gửi cho Google.
        callback_url = current_app.config["GOOGLE_OAUTH_REDIRECT_URI"]
        if request.query_string:
            callback_url = f"{callback_url}?{request.query_string.decode('ascii')}"
        flow.fetch_token(authorization_response=callback_url)
        save_credentials(flow.credentials)
        flash("Đã kết nối Google Drive. Người dùng có thể tải ảnh minh chứng trực tiếp.", "success")
    except Exception as exc:
        current_app.logger.exception("Kết nối Google Drive thất bại: %s", exc)
        error_text = str(exc).lower()
        if "invalid_client" in error_text:
            message = "Google từ chối Client ID hoặc Client Secret. Hãy kiểm tra biến môi trường trên Render."
        elif "invalid_grant" in error_text:
            message = "Mã xác thực Google đã hết hạn hoặc đã được dùng. Hãy kết nối lại từ đầu."
        elif "redirect_uri" in error_text:
            message = "Redirect URI chưa khớp chính xác giữa Render và Google Cloud."
        elif "insecure_transport" in error_text:
            message = "Máy chủ chưa nhận diện kết nối HTTPS. Hãy deploy phiên bản mới nhất."
        else:
            message = "Kết nối Google Drive thất bại. Hãy xem Logs trên Render để biết chi tiết."
        flash(message, "error")
    return redirect(url_for("admin.dashboard"))


def get_match_or_404(match_id):
    try:
        return get_db().matches.find_one_or_404({"_id": ObjectId(match_id)})
    except Exception:
        from flask import abort
        abort(404)


@admin_bp.post("/tran/<match_id>/duyet")
@admin_required
def approve(match_id):
    db = get_db()
    match = db.matches.find_one({"_id": ObjectId(match_id)})
    if match:
        if message := locked_match_message(db, match):
            flash(message, "error")
            return redirect(request.referrer or url_for("admin.dashboard"))
        db.matches.update_one({"_id": match["_id"]}, {"$set": {
            "status": "approved", "approved_at": datetime.utcnow(), "updated_at": datetime.utcnow(),
            "admin_note": request.form.get("admin_note", "").strip(),
        }})
        log_action("approve", match)
        flash(f"Đã duyệt {match['match_code']}.", "success")
    return redirect(request.referrer or url_for("admin.dashboard"))


@admin_bp.post("/tran/<match_id>/tu-choi")
@admin_required
def reject(match_id):
    db = get_db()
    match = db.matches.find_one({"_id": ObjectId(match_id)})
    if match:
        if message := locked_match_message(db, match):
            flash(message, "error")
            return redirect(request.referrer or url_for("admin.dashboard"))
        note = request.form.get("admin_note", "").strip() or "Bản ghi chưa đáp ứng điều kiện."
        db.matches.update_one({"_id": match["_id"]}, {"$set": {
            "status": "rejected", "admin_note": note, "updated_at": datetime.utcnow(),
        }})
        log_action("reject", match, note)
        flash(f"Đã từ chối {match['match_code']}.", "success")
    return redirect(request.referrer or url_for("admin.dashboard"))


@admin_bp.post("/tran/<match_id>/xoa")
@admin_required
def delete(match_id):
    db = get_db()
    match = db.matches.find_one({"_id": ObjectId(match_id)})
    if match:
        if message := locked_match_message(db, match):
            flash(message, "error")
            return redirect(request.referrer or url_for("admin.dashboard"))
        log_action("delete", match)
        db.matches.delete_one({"_id": match["_id"]})
        flash(f"Đã xóa {match['match_code']}.", "success")
    return redirect(request.referrer or url_for("admin.dashboard"))


@admin_bp.post("/mua-giai/<month>/khoa")
@admin_required
def toggle_lock(month):
    db = get_db()
    current = db.seasons.find_one({"month": month}) or {}
    locked = not current.get("locked", False)
    db.seasons.update_one(
        {"month": month},
        {"$set": {"month": month, "locked": locked, "updated_at": datetime.utcnow()}},
        upsert=True,
    )
    log_action("lock_season" if locked else "unlock_season", details=month)
    flash(f"Đã {'khóa' if locked else 'mở'} mùa giải {month}.", "success")
    return redirect(request.referrer or url_for("admin.dashboard", month=month))
