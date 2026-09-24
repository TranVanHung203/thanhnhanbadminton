from datetime import datetime
import re
from zoneinfo import ZoneInfo


LOCAL_TIMEZONE = ZoneInfo("Asia/Ho_Chi_Minh")


def current_month(now=None):
    """Trả về khóa mùa giải YYYY-MM theo giờ Việt Nam."""
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


def available_months(db, selected=None):
    """Tháng hiện tại + mọi tháng đã có trận/mùa giải, mới nhất trước."""
    values = set(db.matches.distinct("month"))
    values.update(db.seasons.distinct("month"))
    values.add(current_month())
    if selected:
        values.add(selected)
    return sorted((value for value in values if value), reverse=True)
