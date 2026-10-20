from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from app import create_app
from app.services.seasons import active_month, available_months, current_month, next_month, normalize_month


def test_calendar_month_uses_local_timezone():
    timezone = ZoneInfo("Asia/Ho_Chi_Minh")
    assert current_month(datetime(2026, 9, 30, 23, 59, tzinfo=timezone)) == "2026-09"
    assert current_month(datetime(2026, 10, 1, 0, 1, tzinfo=timezone)) == "2026-10"


def test_normalize_month_accepts_any_valid_year_and_rejects_invalid_month():
    assert normalize_month("2037-01", "2026-09") == "2037-01"
    assert normalize_month("1999-12", "2026-09") == "1999-12"
    assert normalize_month("2026-13", "2026-09") == "2026-09"


class Cursor(list):
    def sort(self, *args):
        # The route tests use empty match lists; only the query matters here.
        return self


class Collection:
    def __init__(self):
        self.items = []

    def find(self, query):
        return Cursor(item for item in self.items if all(
            item.get(key) in value["$in"] if isinstance(value, dict) else item.get(key) == value
            for key, value in query.items()
        ))

    def find_one(self, query):
        return next(iter(self.find(query)), None)

    def distinct(self, field):
        return list({item[field] for item in self.items if field in item})

    def insert_one(self, document):
        self.items.append(dict(document))
        return SimpleNamespace(inserted_id="test-match")

    def update_one(self, query, update, upsert=False):
        item = self.find_one(query)
        inserted = item is None
        if inserted:
            if not upsert:
                return SimpleNamespace(modified_count=0)
            item = dict(query)
            self.items.append(item)
            item.update(update.get("$setOnInsert", {}))
        before = dict(item)
        item.update(update.get("$set", {}))
        return SimpleNamespace(modified_count=int(not inserted and item != before))


@pytest.fixture
def league(monkeypatch):
    db = SimpleNamespace(**{name: Collection() for name in (
        "app_settings", "seasons", "matches", "audit_logs",
    )})
    for module in ("public", "admin", "api"):
        monkeypatch.setattr(f"app.routes.{module}.get_db", lambda: db)
    monkeypatch.setattr("app.routes.admin.token_summary", lambda: {})
    monkeypatch.setattr("app.services.seasons.current_month", lambda: "2026-09")
    app = create_app({"TESTING": True, "SECRET_KEY": "season-tests"})
    client = app.test_client()
    with client.session_transaction() as session:
        session["is_admin"] = True
    return db, client


def test_empty_database_pins_initial_season_across_calendar_changes(league, monkeypatch):
    db, _ = league
    assert active_month(db) == "2026-09"
    monkeypatch.setattr("app.services.seasons.current_month", lambda: "2027-02")
    assert active_month(db) == "2026-09"
    assert available_months(db) == ["2026-09"]


@pytest.mark.parametrize("source", ["matches", "seasons"])
def test_upgrade_keeps_existing_unlocked_season(league, monkeypatch, source):
    db, _ = league
    getattr(db, source).insert_one({"month": "2026-08"})
    monkeypatch.setattr("app.services.seasons.current_month", lambda: "2026-12")
    assert active_month(db) == "2026-08"


def test_upgrade_continues_after_last_locked_season(league):
    db, _ = league
    db.seasons.insert_one({"month": "2026-07", "locked": True})
    assert active_month(db) == "2026-08"


@pytest.mark.parametrize("path", ["/", "/ket-qua", "/nhap-ket-qua", "/admin/", "/admin/boc-tham", "/api/results"])
def test_all_default_pages_keep_active_season(league, monkeypatch, path):
    db, client = league
    active_month(db)
    monkeypatch.setattr("app.services.seasons.current_month", lambda: "2027-01")
    response = client.get(path)
    assert response.status_code == 200
    if path == "/api/results":
        assert response.json["month"] == "2026-09"
    else:
        assert "09/2026" in response.get_data(as_text=True) or 'value="2026-09"' in response.get_data(as_text=True)
    assert active_month(db) == "2026-09"


def test_lock_advances_exactly_one_month_and_preserves_history(league, monkeypatch):
    db, client = league
    active_month(db)
    monkeypatch.setattr("app.services.seasons.current_month", lambda: "2027-03")
    response = client.post("/admin/mua-giai/2026-09/khoa", headers={"Referer": "/admin/?month=2026-09"})
    assert response.status_code == 302
    assert response.location.endswith("/admin/?month=2026-10")
    assert active_month(db) == "2026-10"
    assert db.seasons.find_one({"month": "2026-09"})["locked"] is True
    assert db.seasons.find_one({"month": "2026-10"})["locked"] is False
    assert available_months(db) == ["2026-10", "2026-09"]
    assert client.get("/api/results").json["month"] == "2026-10"
    assert client.get("/api/results?month=2026-09").json["month"] == "2026-09"


def test_reopening_and_relocking_history_does_not_advance_again(league):
    db, client = league
    client.post("/admin/mua-giai/2026-09/khoa")
    client.post("/admin/mua-giai/2026-09/khoa")
    assert db.seasons.find_one({"month": "2026-09"})["locked"] is False
    assert active_month(db) == "2026-10"
    client.post("/admin/mua-giai/2026-09/khoa")
    assert db.seasons.find_one({"month": "2026-09"})["locked"] is True
    assert active_month(db) == "2026-10"


def test_lock_december_opens_january_of_next_year(league):
    db, client = league
    db.seasons.insert_one({"month": "2026-12", "locked": False})
    response = client.post("/admin/mua-giai/2026-12/khoa")
    assert next_month("2026-12") == "2027-01"
    assert active_month(db) == "2027-01"
    assert response.location.endswith("month=2027-01")


def extended_match():
    return {
        "month": "2026-09", "played_date": "2026-10-02", "played_time": "18:00",
        "stage": "final", "result_status": "completed",
        "player_a": "A", "player_b": "B", "referee_1": "C", "referee_2": "D",
        "set1_a": 15, "set1_b": 10, "set2_a": 15, "set2_b": 12,
    }


def test_extended_match_stays_in_open_season_and_lock_blocks_stale_form(league):
    db, client = league
    response = client.post("/api/matches", json=extended_match())
    assert response.status_code == 201
    assert db.matches.items[0]["month"] == "2026-09"
    assert db.matches.items[0]["played_date"] == "2026-10-02"
    client.post("/admin/mua-giai/2026-09/khoa")
    assert client.post("/api/matches", json=extended_match()).status_code == 423
    assert client.get("/nhap-ket-qua?month=2026-09").status_code == 423


def test_future_season_cannot_be_started_before_lock(league):
    db, client = league
    payload = {**extended_match(), "month": "2026-10", "stage": "group"}
    assert client.post("/api/matches", json=payload).status_code == 409
    assert client.get("/nhap-ket-qua?month=2026-10").status_code == 409
    assert client.post("/admin/mua-giai/2026-10/khoa").status_code == 409
    assert active_month(db) == "2026-09"
    assert db.matches.items == []


def test_lock_requires_admin_session(league):
    db, client = league
    with client.session_transaction() as session:
        session.clear()
    assert client.post("/admin/mua-giai/2026-09/khoa").status_code == 302
    assert db.seasons.items == []
