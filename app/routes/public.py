from pathlib import Path

from flask import Blueprint, abort, current_app, render_template, request, send_file

from ..db import get_db
from ..services.ranking import calculate_awards, calculate_contributors, calculate_rankings, summarize
from ..services.seasons import available_months, current_month, normalize_month


public_bp = Blueprint("public", __name__)


def month_context(selected=None):
    db = get_db()
    selected = normalize_month(selected or request.args.get("month"), current_month())
    months = available_months(db, selected)
    matches = list(db.matches.find({"month": selected}).sort("submitted_at", -1))
    rankings = calculate_rankings(matches)
    season = db.seasons.find_one({"month": selected}) or {"month": selected, "locked": False}
    return selected, months, matches, rankings, season


@public_bp.route("/")
def home():
    try:
        month, months, matches, rankings, season = month_context()
        stats = summarize(matches, rankings)
        recent = [item for item in matches if item.get("status") == "approved"][:5]
        db_error = None
    except Exception as exc:
        current_app.logger.error("MongoDB error: %s", exc)
        month, months, matches, rankings, season = current_month(), [current_month()], [], [], {"locked": False}
        stats, recent, db_error = summarize([], []), [], "Chưa kết nối được cơ sở dữ liệu."
    return render_template(
        "home.html", month=month, months=months, rankings=rankings[:8],
        stats=stats, recent=recent, season=season, db_error=db_error,
    )


@public_bp.get("/thanh-nhan-logo.png")
def brand_logo():
    logo_path = Path(current_app.root_path).parent / "thanh_nhan_new.png"
    return send_file(logo_path, mimetype="image/png", max_age=86400)


@public_bp.route("/nhap-ket-qua")
def submit_result():
    month = normalize_month(request.args.get("month"), current_month())
    try:
        season = get_db().seasons.find_one({"month": month}) or {"locked": False}
    except Exception:
        season = {"locked": False}
    if season.get("locked"):
        abort(423)
    return render_template(
        "submit.html",
        month=month,
        meta_title="Nhập kết quả thi đấu · Thành Nhân Badminton",
        meta_description=(
            "Gửi kết quả và ảnh minh chứng trận đấu của Giải cầu lông "
            "Thành Nhân hằng tháng."
        ),
    )


@public_bp.route("/ket-qua")
def results():
    month, months, matches, rankings, season = month_context()
    approved = [item for item in matches if item.get("status") == "approved"]
    contributors = calculate_contributors(matches)
    awards = calculate_awards(
        matches, rankings, contributors, locked=season.get("locked", False),
        decisions=season.get("award_decisions", {}),
    )
    return render_template(
        "results.html", month=month, months=months, matches=approved,
        rankings=rankings, contributors=contributors, awards=awards, season=season,
    )


@public_bp.route("/the-le")
def rules():
    return render_template("rules.html")
