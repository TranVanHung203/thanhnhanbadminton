from datetime import datetime, timedelta, timezone
from hashlib import sha256
import re
from secrets import compare_digest, token_urlsafe

from bson import ObjectId
from flask import Blueprint, abort, current_app, flash, g, redirect, render_template, request, session, url_for
from pymongo.errors import PyMongoError

from ..db import get_db


forum_bp = Blueprint("forum", __name__, url_prefix="/dien-dan")
PAGE_SIZE = 20
COMMENT_PAGE_SIZE = 50
VISIBLE = {"deleted_at": {"$exists": False}}
OWNER_COOKIE = "forum_owner"


@forum_bp.before_request
def identify_owner():
    token = request.cookies.get(OWNER_COOKIE, "")
    if not re.fullmatch(r"[A-Za-z0-9_-]{43}", token):
        token = token_urlsafe(32)
    g.forum_owner_token = token
    g.forum_owner = sha256(token.encode()).hexdigest()


@forum_bp.after_request
def remember_owner(response):
    local_host = request.host.split(":", 1)[0] in {"localhost", "127.0.0.1"}
    response.set_cookie(OWNER_COOKIE, g.forum_owner_token, max_age=365 * 24 * 60 * 60,
                        httponly=True, secure=request.is_secure or not local_host,
                        samesite="Lax", path="/dien-dan")
    response.headers["Cache-Control"] = "private, no-store"
    return response


@forum_bp.context_processor
def ownership_context():
    return {"is_forum_owner": lambda item: item.get("owner_hash") == g.forum_owner}


def csrf_token():
    if "forum_csrf" not in session:
        session["forum_csrf"] = token_urlsafe(32)
    return session["forum_csrf"]


def check_csrf():
    if not compare_digest(session.get("forum_csrf", "").encode(), request.form.get("csrf_token", "").encode()) or not session.get("forum_csrf"):
        abort(400, description="Phiên gửi đã hết hạn. Hãy tải lại trang và thử lại.")


def page_number():
    return max(1, request.args.get("page", 1, type=int) or 1)


def validate_fields(include_title=False):
    limits = {"author_name": (80, "Tên của bạn"), "content": (5000 if include_title else 2000, "Nội dung")}
    if include_title:
        limits["title"] = (160, "Tiêu đề")
    values, errors = {}, []
    for key, (limit, label) in limits.items():
        value = request.form.get(key, "").strip()
        if key in {"author_name", "title"}:
            value = " ".join(value.split())
        values[key] = value
        if not value:
            errors.append(f"Vui lòng nhập {label.lower()}.")
        elif len(value) > limit:
            errors.append(f"{label} tối đa {limit} ký tự.")
    return values, errors


@forum_bp.app_template_filter("forum_time")
def forum_time(value):
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone(timedelta(hours=7))).strftime("%d/%m/%Y · %H:%M")


def listing(values=None, errors=None, status=200):
    page = page_number()
    db_error = None
    try:
        posts = list(get_db().forum_posts.find(VISIBLE).sort([("created_at", -1), ("_id", -1)]).skip((page - 1) * PAGE_SIZE).limit(PAGE_SIZE + 1))
    except PyMongoError:
        current_app.logger.exception("Không thể đọc bài đăng diễn đàn")
        posts, db_error, status = [], "Chưa kết nối được cơ sở dữ liệu. Vui lòng thử lại sau.", 503
    return render_template("forum.html", posts=posts[:PAGE_SIZE], has_next=len(posts) > PAGE_SIZE,
                           page=page, values=values or {}, errors=errors or [], db_error=db_error,
                           csrf_token=csrf_token(), meta_title="Diễn đàn · Thành Nhân Badminton"), status


@forum_bp.route("", methods=["GET", "POST"])
def index():
    if request.method == "GET":
        return listing()
    check_csrf()
    values, errors = validate_fields(include_title=True)
    if errors:
        return listing(values, errors, 422)
    try:
        result = get_db().forum_posts.insert_one({**values, "owner_hash": g.forum_owner, "created_at": datetime.now(timezone.utc)})
    except PyMongoError:
        current_app.logger.exception("Không thể lưu bài đăng diễn đàn")
        return listing(values, ["Chưa lưu được bài đăng. Vui lòng thử lại."], 503)
    flash("Đã đăng bài thành công.", "success")
    return redirect(url_for("forum.thread", post_id=str(result.inserted_id)), code=303)


@forum_bp.route("/<post_id>", methods=["GET", "POST"])
def thread(post_id):
    if not ObjectId.is_valid(post_id):
        abort(404)
    if request.method == "POST":
        check_csrf()
    values, errors, status = {}, [], 200
    page = page_number()
    try:
        db = get_db()
        post = db.forum_posts.find_one({"_id": ObjectId(post_id), **VISIBLE})
        if not post:
            abort(404)
        if request.method == "POST":
            values, errors = validate_fields()
            if errors:
                status = 422
            else:
                try:
                    result = db.forum_comments.insert_one({**values, "owner_hash": g.forum_owner, "post_id": post["_id"], "created_at": datetime.now(timezone.utc)})
                except PyMongoError:
                    current_app.logger.exception("Không thể lưu bình luận")
                    errors, status = ["Chưa lưu được bình luận. Vui lòng thử lại."], 503
                else:
                    flash("Đã gửi bình luận.", "success")
                    return redirect(url_for("forum.thread", post_id=post_id, _anchor=f"comment-{result.inserted_id}"), code=303)
        comments = list(db.forum_comments.find({"post_id": post["_id"], **VISIBLE}).sort([("created_at", -1), ("_id", -1)]).skip((page - 1) * COMMENT_PAGE_SIZE).limit(COMMENT_PAGE_SIZE + 1))
        count = db.forum_comments.count_documents({"post_id": post["_id"], **VISIBLE})
    except PyMongoError:
        current_app.logger.exception("Không thể truy cập thảo luận diễn đàn")
        if request.method == "POST":
            values, _ = validate_fields()
        return render_template("forum_unavailable.html", values=values), 503
    return render_template("forum_thread.html", post=post, comments=comments[:COMMENT_PAGE_SIZE],
                           comment_count=count, page=page, has_next=len(comments) > COMMENT_PAGE_SIZE,
                           values=values, errors=errors, csrf_token=csrf_token(),
                           meta_title=f"{post['title']} · Diễn đàn"), status


@forum_bp.post("/<post_id>/xoa")
def delete_post(post_id):
    check_csrf()
    if not ObjectId.is_valid(post_id):
        abort(404)
    try:
        result = get_db().forum_posts.update_one(
            {"_id": ObjectId(post_id), "owner_hash": g.forum_owner, **VISIBLE},
            {"$set": {"deleted_at": datetime.now(timezone.utc)}},
        )
        if not result.matched_count:
            abort(403, description="Bạn chỉ được xóa bài do mình đăng trên trình duyệt này.")
    except PyMongoError:
        current_app.logger.exception("Không thể xóa bài đăng")
        flash("Chưa xóa được bài đăng. Vui lòng thử lại.", "error")
        return redirect(url_for("forum.thread", post_id=post_id), code=303)
    flash("Đã xóa bài đăng khỏi diễn đàn.", "success")
    return redirect(url_for("forum.index"), code=303)


@forum_bp.post("/<post_id>/binh-luan/<comment_id>/xoa")
def delete_comment(post_id, comment_id):
    check_csrf()
    if not ObjectId.is_valid(post_id) or not ObjectId.is_valid(comment_id):
        abort(404)
    try:
        db = get_db()
        if not db.forum_posts.find_one({"_id": ObjectId(post_id), **VISIBLE}):
            abort(404)
        result = db.forum_comments.update_one(
            {"_id": ObjectId(comment_id), "post_id": ObjectId(post_id), "owner_hash": g.forum_owner, **VISIBLE},
            {"$set": {"deleted_at": datetime.now(timezone.utc)}},
        )
        if not result.matched_count:
            abort(403, description="Bạn chỉ được xóa bình luận do mình gửi trên trình duyệt này.")
    except PyMongoError:
        current_app.logger.exception("Không thể xóa bình luận")
        flash("Chưa xóa được bình luận. Vui lòng thử lại.", "error")
        return redirect(url_for("forum.thread", post_id=post_id), code=303)
    flash("Đã xóa bình luận.", "success")
    return redirect(url_for("forum.thread", post_id=post_id), code=303)
