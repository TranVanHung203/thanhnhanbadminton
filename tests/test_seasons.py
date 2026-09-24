from datetime import datetime
from zoneinfo import ZoneInfo

from app.services.seasons import current_month, normalize_month


def test_current_month_changes_automatically():
    timezone = ZoneInfo("Asia/Ho_Chi_Minh")
    assert current_month(datetime(2026, 9, 30, 23, 59, tzinfo=timezone)) == "2026-09"
    assert current_month(datetime(2026, 10, 1, 0, 1, tzinfo=timezone)) == "2026-10"


def test_normalize_month_accepts_any_valid_year_and_rejects_invalid_month():
    assert normalize_month("2037-01", "2026-09") == "2037-01"
    assert normalize_month("1999-12", "2026-09") == "1999-12"
    assert normalize_month("2026-13", "2026-09") == "2026-09"
