from flask import render_template

from app import create_app
from app.services.ranking import calculate_awards, calculate_player_details, calculate_rankings
from test_ranking import make_match


def test_player_history_matches_ranking_totals_and_normalizes_names():
    matches = [make_match(i, "An", f"Đối thủ {i}") for i in range(1, 10)]
    matches[3]["player_a"] = " an "
    matches.append(make_match(10, "An", "Bình", stage="final"))
    referee_match = make_match(11, "Bình", "Chi")
    referee_match["referee_1"] = "AN"
    matches.append(referee_match)
    paused = make_match(12, "An", "Dũng")
    paused["result_status"] = "paused"
    matches.append(paused)
    pending = make_match(13, "An", "Không công khai")
    pending["status"] = "pending"
    matches.append(pending)
    rankings = calculate_rankings(matches)
    awards = calculate_awards(matches, rankings)
    profile = next(p for p in calculate_player_details(list(reversed(matches)), rankings, awards)
                   if p["summary"]["name"] == "An")
    history = profile["matches"]
    summary = profile["summary"]
    assert len(history) == 11
    assert history[0]["result"] == "Tạm dừng"
    assert history[0]["points"] == 0
    assert history[2]["category"] == "Vượt số trận tính điểm"
    assert sum(item["points"] for item in history) == summary["total_points"]
    assert sum(item["stars"] for item in history) == summary["stars"]
    assert sum(item["flowers"] for item in profile["refereeing"]) == summary["flowers"]
    assert not any(item["match"]["player_b"] == "Không công khai" for item in history)


def test_valid_forfeit_does_not_use_official_slot_or_earn_flowers():
    forfeited = make_match(1, "An", "Bình")
    forfeited.update(result_status="forfeit", forfeit_side="a", forfeit_reason_valid=True,
                     referee_1="Chi")
    matches = [forfeited, make_match(2, "An", "Chi")]
    rankings = calculate_rankings(matches)
    profiles = calculate_player_details(matches, rankings, calculate_awards(matches, rankings))
    an = next(p for p in profiles if p["summary"]["name"] == "An")
    chi = next(p for p in profiles if p["summary"]["name"] == "Chi")
    assert an["matches"][0]["category"] == "Chính thức"
    assert an["matches"][1]["category"] == "Không tính điểm"
    assert an["matches"][1]["result"] == "Bỏ cuộc"
    assert chi["refereeing"][0]["flowers"] == 0


def test_results_renders_clickable_profile_and_escapes_match_content():
    matches = [make_match(1, '<script>alert("name")</script>', "Bình")]
    matches[0].update(notes='<img src=x onerror=alert(1)>',
                      evidence_urls=["javascript:alert(1)", "https://example.com/evidence"])
    rankings = calculate_rankings(matches)
    awards = calculate_awards(matches, rankings)
    app = create_app({"TESTING": True})
    with app.test_request_context("/ket-qua?month=2026-09"):
        html = render_template("results.html", month="2026-09", rankings=rankings,
                               matches=matches, contributors=[], awards=awards,
                               season={"locked": False},
                               player_details=calculate_player_details(matches, rankings, awards))
    assert 'data-player-details="0"' in html
    assert 'data-player-profile="0"' in html
    assert 'aria-labelledby="player-details-title"' in html
    assert "Lịch sử thi đấu (1 trận)" in html
    assert '<script>alert("name")</script>' not in html
    assert '<img src=x onerror=alert(1)>' not in html
    assert 'href="javascript:' not in html
    assert 'href="https://example.com/evidence"' in html
