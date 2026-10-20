from datetime import datetime
import re
from zoneinfo import ZoneInfo


LOCAL_TIMEZONE = ZoneInfo("Asia/Ho_Chi_Minh")
ACTIVE_SEASON_ID = "active_season"


def current_month(now=None):
    """Tháng trên lịch theo giờ Việt Nam, chỉ dùng để khởi tạo mùa đầu tiên."""
    now = now or datetime.now(LOCAL_TIMEZONE)
    if now.tzinfo is None:
        now = now.replace(tzinfo=LOCAL_TIMEZONE)
    return now.astimezone(LOCAL_TIMEZONE).strftime("%Y-%m")


def normalize_month(value, fallback=None):
    """Chuẩn hóa tháng từ URL; cho phép chọn mọi năm bốn chữ số."""
    value = str(value or "").strip()
    if re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", value):
        return value
    return fallback or current_month()


def next_month(month):
    year, number = map(int, month.split("-"))
    return f"{year + (number == 12):04d}-{number % 12 + 1:02d}"


def active_month(db):
    """Lưu mùa hiện tại độc lập với lịch; giữ nguyên qua tháng/năm mới."""
    setting = db.app_settings.find_one({"_id": ACTIVE_SEASON_ID})
    if setting:
        return setting["month"]

    # Khi nâng cấp, tiếp tục mùa mới nhất đã có dữ liệu. Chỉ dùng lịch
    # khi chưa từng có mùa nào, tránh bỏ qua mùa đang thi đấu dở.
    months = set(db.matches.distinct("month")) | set(db.seasons.distinct("month"))
    months = [month for month in months if month and normalize_month(month) == month]
    month = max(months) if months else current_month()
    season = db.seasons.find_one({"month": month}) or {}
    if season.get("locked"):
        month = next_month(month)
    db.app_settings.update_one(
        {"_id": ACTIVE_SEASON_ID},
        {"$setOnInsert": {"month": month}},
        upsert=True,
    )
    return db.app_settings.find_one({"_id": ACTIVE_SEASON_ID})["month"]


def advance_season(db, month):
    """Chỉ khóa mùa hiện tại mới chuyển sang tháng liền kề, không nhảy theo lịch."""
    following = next_month(month)
    result = db.app_settings.update_one(
        {"_id": ACTIVE_SEASON_ID, "month": month},
        {"$set": {"month": following}},
    )
    if result.modified_count:
        db.seasons.update_one(
            {"month": following},
            {"$setOnInsert": {"month": following, "locked": False}},
            upsert=True,
        )
        return following
    return None


def available_months(db, selected=None):
    """Mùa hiện tại và lịch sử, không tự thêm tháng mới theo lịch."""
    values = set(db.matches.distinct("month"))
    values.update(db.seasons.distinct("month"))
    values.add(active_month(db))
    if selected:
        values.add(selected)
    return sorted((value for value in values if value), reverse=True)
