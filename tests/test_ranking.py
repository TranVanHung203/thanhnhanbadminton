from datetime import datetime, timedelta

from app.services.ranking import calculate_awards, calculate_contributors, calculate_rankings


def make_match(number, player_a, player_b, winner="a", stage="group"):
    sets = [{"a": 15, "b": 10}, {"a": 15, "b": 11}]
    if winner == "b":
        sets = [{"a": 10, "b": 15}, {"a": 11, "b": 15}]
    return {
        "status": "approved",
        "submitted_at": datetime(2026, 9, 1) + timedelta(minutes=number),
        "player_a": player_a,
        "player_b": player_b,
        "referee_1": f"Trọng tài {number}A",
        "referee_2": f"Trọng tài {number}B",
        "stage": stage,
        "result_status": "completed",
        "sets": sets,
    }


def find(rows, name):
    return next(row for row in rows if row["name"] == name)


def test_first_three_are_official_next_five_are_unofficial():
    matches = [make_match(i, "An", f"Đối thủ {i}") for i in range(1, 10)]
    an = find(calculate_rankings(matches), "An")
    assert an["official_matches"] == 3
    assert an["official_points"] == 9
    assert an["unofficial_matches"] == 5
    assert an["stars"] == 15


def test_final_points_are_added_without_stars():
    matches = [make_match(1, "An", "Bình"), make_match(2, "An", "Bình", stage="final")]
    an = find(calculate_rankings(matches), "An")
    assert an["official_points"] == 3
    assert an["final_points"] == 3
    assert an["total_points"] == 6
    assert an["stars"] == 0


def test_final_round_uses_set_difference_after_points_and_stars_are_equal():
    matches = [
        make_match(1, "An", "Bình", stage="final"),
        make_match(2, "Bình", "Cường", stage="final"),
        make_match(3, "Cường", "An", stage="final"),
    ]
    matches[2]["sets"] = [
        {"a": 15, "b": 10},
        {"a": 10, "b": 15},
        {"a": 15, "b": 13},
    ]

    rows = calculate_rankings(matches)

    assert find(rows, "An")["final_points"] == 4
    assert find(rows, "Bình")["final_points"] == 4
    assert find(rows, "Cường")["final_points"] == 4
    assert find(rows, "An")["final_set_difference"] == 1
    assert find(rows, "An")["rank"] == 1
    assert find(rows, "Bình")["rank"] == 2
    assert find(rows, "Cường")["rank"] == 3


def test_referee_only_is_not_in_player_ranking():
    matches = [make_match(1, "An", "Bình")]
    rows = calculate_rankings(matches)
    assert {row["name"] for row in rows} == {"An", "Bình"}
    contributors = calculate_contributors(matches)
    assert {item["name"] for item in contributors} == {"Trọng tài 1A", "Trọng tài 1B"}
    assert all(item["flowers"] == 1 for item in contributors)


def test_player_who_also_referees_keeps_flowers_without_extra_row():
    first = make_match(1, "An", "Bình")
    second = make_match(2, "Cường", "Dũng")
    second["referee_1"] = "An"
    rows = calculate_rankings([first, second])
    assert find(rows, "An")["flowers"] == 1
    assert len([row for row in rows if row["name"] == "An"]) == 1


def test_only_top_tie_requires_final_round():
    matches = [
        make_match(1, "An", "Cường"),
        make_match(2, "Bình", "Dũng"),
    ]
    rows = calculate_rankings(matches)
    assert find(rows, "An")["tie_status"] == "final_round"
    assert find(rows, "Bình")["tie_status"] == "final_round"
    assert find(rows, "Cường")["tie_status"] == "equal_result"
    assert find(rows, "Dũng")["tie_status"] == "equal_result"
    assert not any(row["award"] for row in rows)
    assert find(rows, "Cường")["award_status"] == "waiting_ranking"


def test_achievement_awards_follow_one_first_and_three_seconds():
    matches = [
        make_match(1, "An", "Bình"),
        make_match(2, "An", "Cường"),
        make_match(3, "An", "Dũng"),
        make_match(4, "Bình", "Cường"),
        make_match(5, "Bình", "Dũng"),
        make_match(6, "Cường", "Dũng"),
    ]
    rows = calculate_rankings(matches)
    assert find(rows, "An")["award"] == "Giải Nhất"
    assert {row["name"] for row in rows if row["award"] == "Giải Nhì"} == {"Bình", "Cường", "Dũng"}


def test_attitude_awards_are_ordered_and_previous_winners_are_excluded():
    match = make_match(1, "Dũng cảm", "Vô địch")
    rankings = [
        {
            "name": "Vô địch", "rank": 1, "award": "Giải Nhất", "award_status": "",
            "official_matches": 3, "unofficial_completed": 0, "stars": 0,
        },
        {
            "name": "Dũng cảm", "rank": 2, "award": "Giải Nhì", "award_status": "",
            "official_matches": 3, "unofficial_completed": 3, "stars": 9,
        },
        {
            "name": "Ngôi sao", "rank": 3, "award": "Giải Nhì", "award_status": "",
            "official_matches": 3, "unofficial_completed": 2, "stars": 6,
        },
    ]
    contributors = [
        {"name": "Dũng cảm", "flowers": 10, "matches": 10, "rank": 1},
        {"name": "Ngôi sao", "flowers": 8, "matches": 8, "rank": 2},
        {"name": "Đồng hành", "flowers": 7, "matches": 7, "rank": 3},
    ]
    awards = calculate_awards([match], rankings, contributors, locked=True)
    attitude = {item["key"]: item for item in awards["attitude"]["items"]}
    assert attitude["head_to_head"]["recipients"][0]["name"] == "Dũng cảm"
    assert attitude["active_star"]["recipients"][0]["name"] == "Ngôi sao"
    assert attitude["active_flower"]["recipients"][0]["name"] == "Đồng hành"
    assert awards["status_label"] == "Chính thức"


def test_head_to_head_uses_the_highest_available_priority_level():
    rankings = [
        {"name": "Nhất", "rank": 1, "award": "Giải Nhất", "award_status": "", "official_matches": 3, "unofficial_completed": 0, "stars": 0},
        {"name": "Nhì 1", "rank": 2, "award": "Giải Nhì", "award_status": "", "official_matches": 3, "unofficial_completed": 0, "stars": 0},
        {"name": "Nhì 2", "rank": 3, "award": "Giải Nhì", "award_status": "", "official_matches": 3, "unofficial_completed": 0, "stars": 0},
        {"name": "Nhì 3", "rank": 4, "award": "Giải Nhì", "award_status": "", "official_matches": 3, "unofficial_completed": 0, "stars": 0},
        {"name": "Ba 1", "rank": 5, "award": "Giải Ba", "award_status": "", "official_matches": 3, "unofficial_completed": 0, "stars": 0},
        {"name": "Ba 2", "rank": 6, "award": "Giải Ba", "award_status": "", "official_matches": 3, "unofficial_completed": 0, "stars": 0},
        {"name": "Ưu tiên 2", "rank": 7, "award": "Giải Ba", "award_status": "", "official_matches": 3, "unofficial_completed": 0, "stars": 0},
        {"name": "Ưu tiên 3", "rank": 8, "award": "Giải Ba", "award_status": "", "official_matches": 3, "unofficial_completed": 0, "stars": 0},
    ]
    matches = [
        make_match(1, "Ưu tiên 2", "Nhì 1"),
        make_match(2, "Ưu tiên 2", "Nhì 2"),
        make_match(3, "Ưu tiên 3", "Nhì 3"),
        make_match(4, "Ưu tiên 3", "Ba 1"),
        make_match(5, "Ưu tiên 3", "Ba 2"),
    ]

    awards = calculate_awards(matches, rankings, [])
    head_to_head = awards["attitude"]["items"][0]

    assert head_to_head["status"] == "winner"
    assert head_to_head["recipients"][0]["name"] == "Ưu tiên 2"
    assert head_to_head["recipients"][0]["priority"] == 2


def test_head_to_head_tie_is_not_awarded_and_does_not_block_star_award():
    rankings = [
        {"name": "Nhất", "rank": 1, "award": "Giải Nhất", "award_status": "", "official_matches": 3, "unofficial_completed": 0, "stars": 0},
        {"name": "A", "rank": 2, "award": "Giải Nhì", "award_status": "", "official_matches": 3, "unofficial_completed": 2, "stars": 6},
        {"name": "B", "rank": 3, "award": "Giải Nhì", "award_status": "", "official_matches": 3, "unofficial_completed": 1, "stars": 3},
    ]
    matches = [make_match(1, "A", "Nhất"), make_match(2, "B", "Nhất")]

    awards = calculate_awards(matches, rankings, [])
    head_to_head, active_star, _ = awards["attitude"]["items"]

    assert head_to_head["status"] == "tied_unawarded"
    assert head_to_head["recipients"] == []
    assert {item["name"] for item in head_to_head["candidates"]} == {"A", "B"}
    assert active_star["recipients"][0]["name"] == "A"


def test_award_budget_matches_the_published_prize_structure():
    awards = calculate_awards([], [], [])
    achievement = {item["key"]: item for item in awards["achievement"]["items"]}
    attitude = {item["key"]: item for item in awards["attitude"]["items"]}

    assert achievement["third"]["prize"] == 100_000
    assert attitude["head_to_head"]["prize"] == 500_000
    assert awards["achievement"]["budget"] == 1_600_000
    assert awards["attitude"]["budget"] == 1_000_000
    assert awards["total_budget"] == 2_600_000


def test_saved_boundary_draw_assigns_second_and_remaining_thirds():
    def award_row(name, rank, award="", status=""):
        return {
            "name": name, "rank": rank, "award": award, "award_status": status,
            "award_note": "", "official_matches": 3, "unofficial_completed": 0,
            "stars": 0, "flowers": 0,
        }

    rankings = [
        award_row("Nhất", 1, "Giải Nhất"),
        award_row("Nhì 1", 2, "Giải Nhì"),
        award_row("Nhì 2", 3, "Giải Nhì"),
        award_row("Ứng viên A", 4, status="draw_second"),
        award_row("Ứng viên B", 4, status="draw_second"),
        award_row("Ứng viên C", 4, status="draw_second"),
        award_row("Ứng viên D", 4, status="draw_second"),
    ]
    before = calculate_awards([], rankings, [], decisions={})
    assert before["draws"][0]["key"] == "achievement_second"
    assert before["draws"][0]["slots"] == 1

    rankings = [dict(row) for row in rankings]
    after = calculate_awards(
        [], rankings, [], decisions={"achievement_second": ["Ứng viên C"]}
    )
    assert find(rankings, "Ứng viên C")["award"] == "Giải Nhì"
    assert {
        row["name"] for row in rankings if row["award"] == "Giải Ba"
    } == {"Ứng viên A", "Ứng viên B", "Ứng viên D"}
    assert not after["draws"]


def test_saved_manual_star_decision_resolves_tie():
    rankings = [
        {"name": "A", "rank": 1, "award": "Giải Nhất", "award_status": "", "award_note": "", "official_matches": 3, "unofficial_completed": 0, "stars": 0, "flowers": 0},
        {"name": "B", "rank": 2, "award": "Giải Nhì", "award_status": "", "award_note": "", "official_matches": 3, "unofficial_completed": 2, "stars": 5, "flowers": 0},
        {"name": "C", "rank": 3, "award": "Giải Nhì", "award_status": "", "award_note": "", "official_matches": 3, "unofficial_completed": 2, "stars": 5, "flowers": 0},
    ]
    before = calculate_awards([], [dict(row) for row in rankings], [])
    assert before["draws"][0]["key"] == "active_star"
    after = calculate_awards(
        [], [dict(row) for row in rankings], [], decisions={"active_star": "C"}
    )
    star = next(item for item in after["attitude"]["items"] if item["key"] == "active_star")
    assert star["recipients"][0]["name"] == "C"
