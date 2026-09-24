from flask import render_template

from app import create_app


def test_home_prioritizes_award_label_for_tied_player():
    app = create_app({"TESTING": True})
    tied_third = {
        "rank": 5,
        "name": "Người đạt Giải Ba",
        "official_wins": 1,
        "official_losses": 0,
        "official_matches": 1,
        "official_points": 3,
        "stars": 0,
        "flowers": 0,
        "total_points": 3,
        "award_status": "",
        "award": "Giải Ba",
        "tied": True,
    }

    with app.test_request_context("/", base_url="https://example.com"):
        html = render_template(
            "home.html",
            month="2026-09",
            rankings=[tied_third],
            stats={
                "approved_matches": 1,
                "players": 1,
                "flowers": 0,
                "pending_matches": 0,
            },
            recent=[],
            season={"locked": False},
            db_error=None,
        )

    assert "Giải Ba" in html
    assert "Đồng thành tích" not in html


def test_draw_wheel_itself_is_the_only_spin_control():
    app = create_app({"TESTING": True})
    task = {
        "key": "achievement_third",
        "award_title": "Giải Ba",
        "title": "Bốc thăm Giải Ba",
        "description": "Chọn người nhận giải.",
        "slots": 1,
        "candidates": [{"name": "Vận động viên A"}, {"name": "Vận động viên B"}],
    }

    with app.test_request_context(
        "/admin/boc-tham?month=2026-09", base_url="https://example.com"
    ):
        html = render_template(
            "admin/draw.html",
            month="2026-09",
            season={"locked": False},
            awards={"draws": [task], "decisions": {}},
            history=[],
        )

    assert html.count("data-spin-wheel") == 1
    assert 'class="wheel-stage wheel-trigger"' in html
    assert "Chạm vào vòng quay để bắt đầu" in html
    assert "QUAY BỐC THĂM" not in html
    assert "<span>THÀNH NHÂN</span>" not in html
