from collections import defaultdict

from .validation import identity, match_winner


ACHIEVEMENT_AWARDS = (
    {"key": "first", "title": "Giải Nhất", "quantity": 1, "prize": 500_000},
    {"key": "second", "title": "Giải Nhì", "quantity": 3, "prize": 200_000},
    {"key": "third", "title": "Giải Ba", "quantity": 5, "prize": 100_000},
)

ATTITUDE_AWARDS = (
    {"key": "head_to_head", "title": "Tay vợt có thành tích đối đầu ấn tượng", "prize": 500_000},
    {"key": "active_star", "title": "Ngôi sao thi đấu tích cực", "prize": 250_000},
    {"key": "active_flower", "title": "Hoa đồng hành tích cực", "prize": 250_000},
)


def _blank(name):
    return {
        "name": name,
        "official_matches": 0,
        "official_wins": 0,
        "official_losses": 0,
        "official_points": 0,
        "unofficial_matches": 0,
        "unofficial_completed": 0,
        "unofficial_wins": 0,
        "stars": 0,
        "flowers": 0,
        "final_matches": 0,
        "final_wins": 0,
        "final_points": 0,
        "final_head_to_head_wins": 0,
        "final_set_difference": 0,
        "final_point_difference": 0,
        "total_points": 0,
        "rank": None,
        "award": "",
        "award_status": "",
        "award_note": "",
        "tied": False,
        "tie_status": "",
    }


def _winner(match):
    winner = match_winner(match.get("sets", [])) if match.get("result_status") == "completed" else None
    if match.get("result_status") == "forfeit" and not match.get("forfeit_reason_valid"):
        winner = "b" if match.get("forfeit_side") == "a" else "a"
    return winner


def _is_countable(match):
    return not (
        match.get("result_status") == "paused"
        or (match.get("result_status") == "forfeit" and match.get("forfeit_reason_valid"))
    )


def _final_tiebreak_statistics(matches, candidate_names):
    """Tính đối đầu, hiệu số set và hiệu số điểm trong nhóm còn đồng hạng Nhất."""
    candidate_keys = {identity(name) for name in candidate_names}
    stats = {
        key: {"head_to_head_wins": 0, "set_difference": 0, "point_difference": 0}
        for key in candidate_keys
    }

    for match in matches:
        if (
            match.get("status") != "approved"
            or match.get("stage") != "final"
            or not _is_countable(match)
        ):
            continue
        a_key = identity(match.get("player_a"))
        b_key = identity(match.get("player_b"))
        if a_key not in candidate_keys or b_key not in candidate_keys:
            continue

        winner = _winner(match)
        if winner == "a":
            stats[a_key]["head_to_head_wins"] += 1
        elif winner == "b":
            stats[b_key]["head_to_head_wins"] += 1

        for played_set in match.get("sets", []):
            a_points, b_points = played_set["a"], played_set["b"]
            if a_points > b_points:
                stats[a_key]["set_difference"] += 1
                stats[b_key]["set_difference"] -= 1
            else:
                stats[a_key]["set_difference"] -= 1
                stats[b_key]["set_difference"] += 1
            stats[a_key]["point_difference"] += a_points - b_points
            stats[b_key]["point_difference"] += b_points - a_points

    return stats


def _assign_achievement_labels(rows):
    """Gắn giải khi đã xác định được người nhận; không tự phá đồng hạng."""
    for row in rows:
        row["award"] = ""
        row["award_status"] = ""
        row["award_note"] = ""

    if not rows:
        return

    top_group = [row for row in rows if row["rank"] == 1]
    if len(top_group) > 1:
        has_final = any(row["final_matches"] for row in rows)
        status = "final_tiebreak" if has_final else "final_round"
        note = (
            "Cần BTC áp dụng đối đầu trực tiếp, hiệu số set/điểm hoặc set quyết định."
            if has_final
            else "Cần thi đấu vòng tròn phân hạng để xác định Giải Nhất."
        )
        for row in top_group:
            row["award_status"] = status
            row["award_note"] = note
        for row in rows[len(top_group):]:
            row["award_status"] = "waiting_ranking"
            row["award_note"] = "Chờ xác định Giải Nhất trước khi phân bổ các giải còn lại."
        return

    groups = []
    for position, row in enumerate(rows, start=1):
        if not groups or groups[-1][0] != row["rank"]:
            groups.append([row["rank"], position, position, [row]])
        else:
            groups[-1][2] = position
            groups[-1][3].append(row)

    for _, start, end, group in groups:
        if start == 1 and end == 1:
            group[0]["award"] = "Giải Nhất"
        elif start >= 2 and end <= 4:
            for row in group:
                row["award"] = "Giải Nhì"
        elif start >= 5 and end <= 9:
            for row in group:
                row["award"] = "Giải Ba"
        elif start <= 4 < end and end <= 9:
            for row in group:
                row["award_status"] = "draw_second"
                row["award_note"] = "Cần bốc thăm công khai tại ranh giới Giải Nhì/Giải Ba."
        elif start <= 9 < end and start >= 5:
            for row in group:
                row["award_status"] = "draw_third"
                row["award_note"] = "Cần bốc thăm công khai để chọn đủ số lượng Giải Ba."
        elif start <= 4 and end > 9:
            for row in group:
                row["award_status"] = "draw_multiple"
                row["award_note"] = "Nhóm đồng thành tích đi qua nhiều ranh giới giải; BTC cần bốc thăm công khai."


def _decision_list(decisions, key):
    value = decisions.get(key, [])
    if isinstance(value, str):
        value = [value]
    return [identity(name) for name in value if name]


def _apply_achievement_decisions(rows, decisions):
    """Áp dụng kết quả bốc thăm đã lưu mà không tự chọn người trong nhóm hòa."""
    second_candidates = [
        row for row in rows if row["award_status"] in {"draw_second", "draw_multiple"}
    ]
    second_slots = max(0, 3 - sum(row["award"] == "Giải Nhì" for row in rows))
    selected_second = _decision_list(decisions, "achievement_second")
    selected_count = 0
    for row in second_candidates:
        if identity(row["name"]) in selected_second and selected_count < second_slots:
            row["award"] = "Giải Nhì"
            row["award_status"] = ""
            row["award_note"] = "Đã được Ban Tổ chức phân định."
            selected_count += 1

    if second_candidates and selected_count < second_slots:
        return

    third_pool = [
        row for row in rows
        if row["award_status"] in {"draw_second", "draw_third", "draw_multiple"}
    ]
    third_slots = max(0, 5 - sum(row["award"] == "Giải Ba" for row in rows))
    selected_third = _decision_list(decisions, "achievement_third")
    selected_third_count = 0
    for row in third_pool:
        if identity(row["name"]) in selected_third and selected_third_count < third_slots:
            row["award"] = "Giải Ba"
            row["award_status"] = ""
            row["award_note"] = "Đã được Ban Tổ chức phân định."
            selected_third_count += 1

    unresolved = [row for row in third_pool if not row["award"]]
    remaining_slots = max(0, third_slots - selected_third_count)
    if len(unresolved) <= remaining_slots:
        for row in unresolved:
            row["award"] = "Giải Ba"
            row["award_status"] = ""
            row["award_note"] = "Được phân bổ sau khi xác định ranh giới Giải Nhì/Giải Ba."
    else:
        for row in unresolved:
            row["award_status"] = "draw_third"
            row["award_note"] = "Cần bốc thăm công khai để chọn đủ số lượng Giải Ba."


def calculate_rankings(matches):
    rows = {}
    appearance = defaultdict(int)
    flowers = defaultdict(int)

    def row(name):
        key = identity(name)
        rows.setdefault(key, _blank(name))
        return rows[key]

    approved = [m for m in matches if m.get("status") == "approved"]
    approved.sort(key=lambda m: (m.get("submitted_at"), str(m.get("_id", ""))))

    for match in approved:
        if not _is_countable(match):
            continue

        a, b = match["player_a"], match["player_b"]
        winner = _winner(match)

        for referee in (match.get("referee_1"), match.get("referee_2")):
            if referee:
                flowers[identity(referee)] += 1

        # Chỉ tạo dòng xếp hạng cho người thực sự thi đấu. Người chỉ làm
        # trọng tài được ghi nhận ở bảng Hoa đồng hành riêng.
        row_a, row_b = row(a), row(b)

        if match.get("stage") == "final":
            for side, current in (("a", row_a), ("b", row_b)):
                current["final_matches"] += 1
                if winner == side:
                    current["final_wins"] += 1
                    current["final_points"] += 3
                else:
                    current["final_points"] += 1 if match.get("result_status") == "completed" else 0
            continue

        for side, name, current in (("a", a, row_a), ("b", b, row_b)):
            key = identity(name)
            appearance[key] += 1
            number = appearance[key]
            won = winner == side
            completed = match.get("result_status") == "completed"
            value = 3 if won else (1 if completed else 0)
            if number <= 3:
                current["official_matches"] += 1
                current["official_wins"] += int(won)
                current["official_losses"] += int(not won)
                current["official_points"] += value
            elif number <= 8:
                current["unofficial_matches"] += 1
                current["unofficial_completed"] += int(completed)
                current["unofficial_wins"] += int(won)
                current["stars"] += value

    result = list(rows.values())
    has_final = any(item["final_matches"] for item in result)
    for item in result:
        item["flowers"] = flowers[identity(item["name"])]
        item["total_points"] = item["official_points"] + item["final_points"]

    # Trước phân hạng: điểm -> đủ 3 trận -> sao.
    # Sau phân hạng: tổng điểm -> sao; nếu vẫn đồng hạng Nhất thì xét đối đầu,
    # hiệu số set và hiệu số điểm của vòng tròn phân hạng.
    if has_final:
        result.sort(key=lambda x: (-x["total_points"], -x["stars"], x["name"].casefold()))
        top_key = (result[0]["total_points"], result[0]["stars"]) if result else None
        top_group = [
            item for item in result
            if (item["total_points"], item["stars"]) == top_key
        ]
        if len(top_group) > 1:
            final_stats = _final_tiebreak_statistics(
                approved, [item["name"] for item in top_group]
            )
            for item in top_group:
                item_stats = final_stats[identity(item["name"])]
                item["final_head_to_head_wins"] = item_stats["head_to_head_wins"]
                item["final_set_difference"] = item_stats["set_difference"]
                item["final_point_difference"] = item_stats["point_difference"]

        top_keys = {identity(item["name"]) for item in top_group}

        def key_func(item):
            if identity(item["name"]) in top_keys:
                return (
                    -item["total_points"],
                    -item["stars"],
                    -item["final_head_to_head_wins"],
                    -item["final_set_difference"],
                    -item["final_point_difference"],
                    item["name"].casefold(),
                )
            return (
                -item["total_points"], -item["stars"], 0, 0, 0,
                item["name"].casefold(),
            )

        def tie_func(item):
            if identity(item["name"]) in top_keys:
                return (
                    item["total_points"],
                    item["stars"],
                    item["final_head_to_head_wins"],
                    item["final_set_difference"],
                    item["final_point_difference"],
                )
            return (item["total_points"], item["stars"], 0, 0, 0)
    else:
        key_func = lambda x: (
            -x["official_points"],
            -(x["official_matches"] >= 3),
            -x["stars"],
            x["name"].casefold(),
        )
        tie_func = lambda x: (x["official_points"], x["official_matches"] >= 3, x["stars"])

    result.sort(key=key_func)
    previous_tie = None
    rank = 0
    for index, item in enumerate(result, start=1):
        current_tie = tie_func(item)
        if current_tie != previous_tie:
            rank = index
        item["rank"] = rank
        previous_tie = current_tie

    groups = defaultdict(list)
    for item in result:
        groups[tie_func(item)].append(item)
    for group in groups.values():
        if len(group) > 1:
            for item in group:
                item["tied"] = True
                if item["rank"] == 1:
                    item["tie_status"] = "final_tiebreak" if has_final else "final_round"
                else:
                    item["tie_status"] = "equal_result"

    _assign_achievement_labels(result)
    return result


def calculate_contributors(matches):
    """Bảng Hoa đồng hành; độc lập với bảng xếp hạng vận động viên."""
    contributors = {}
    approved = [m for m in matches if m.get("status") == "approved"]
    for match in approved:
        if not _is_countable(match):
            continue
        for referee in (match.get("referee_1"), match.get("referee_2")):
            if not referee:
                continue
            key = identity(referee)
            contributors.setdefault(key, {"name": referee, "flowers": 0, "matches": 0})
            contributors[key]["flowers"] += 1
            contributors[key]["matches"] += 1
    result = list(contributors.values())
    result.sort(key=lambda item: (-item["flowers"], item["name"].casefold()))
    previous_flowers = None
    rank = 0
    for index, item in enumerate(result, start=1):
        if item["flowers"] != previous_flowers:
            rank = index
        item["rank"] = rank
        previous_flowers = item["flowers"]
    return result


def _achievement_statistics(rankings):
    unresolved = {
        "final_round", "final_tiebreak", "waiting_ranking",
        "draw_second", "draw_third", "draw_multiple",
    }
    items = []
    for config in ACHIEVEMENT_AWARDS:
        recipients = [
            {"name": row["name"], "rank": row["rank"]}
            for row in rankings if row["award"] == config["title"]
        ]
        if config["key"] == "first":
            candidate_statuses = {"final_round", "final_tiebreak"}
        elif config["key"] == "second":
            candidate_statuses = {"draw_second", "draw_multiple"}
        else:
            candidate_statuses = {"draw_second", "draw_third", "draw_multiple"}
        candidates = [
            {"name": row["name"], "rank": row["rank"], "note": row["award_note"]}
            for row in rankings if row["award_status"] in candidate_statuses
        ]
        item = dict(config)
        item.update({
            "budget": config["quantity"] * config["prize"],
            "recipients": recipients,
            "candidates": candidates,
            "status": "pending" if candidates else ("complete" if len(recipients) == config["quantity"] else "vacant"),
        })
        items.append(item)
    return {
        "items": items,
        "budget": sum(item["budget"] for item in items),
        "allocated": sum(len(item["recipients"]) * item["prize"] for item in items),
        "resolved": not any(row["award_status"] in unresolved for row in rankings),
    }


def _head_to_head_statistics(matches, rankings, achievement_resolved):
    config = dict(ATTITUDE_AWARDS[0])
    if not achievement_resolved:
        config.update({
            "status": "waiting",
            "recipients": [],
            "candidates": [],
            "note": "Chờ hoàn tất phân hạng thành tích để xác định thứ hạng đối thủ.",
            "rows": [],
        })
        return config

    ranking_map = {identity(row["name"]): row for row in rankings}
    appearances = defaultdict(int)
    wins = defaultdict(list)
    approved = [m for m in matches if m.get("status") == "approved"]
    approved.sort(key=lambda m: (m.get("submitted_at"), str(m.get("_id", ""))))

    for match in approved:
        if match.get("stage") != "group" or not _is_countable(match):
            continue
        winner = _winner(match)
        sets = match.get("sets", []) if match.get("result_status") == "completed" else []
        for side, player, opponent in (
            ("a", match["player_a"], match["player_b"]),
            ("b", match["player_b"], match["player_a"]),
        ):
            player_key = identity(player)
            appearances[player_key] += 1
            if appearances[player_key] > 8 or player_key not in ranking_map:
                continue

            opponent_row = ranking_map.get(identity(opponent), _blank(opponent))
            won = winner == side
            opponent_award = opponent_row.get("award", "")
            if not won or opponent_award not in {"Giải Nhất", "Giải Nhì", "Giải Ba"}:
                continue

            other_side = "b" if side == "a" else "a"
            set_wins = sum(1 for item in sets if item[side] > item[other_side])
            set_losses = sum(1 for item in sets if item[side] < item[other_side])
            winning_set_margin = sum(
                item[side] - item[other_side]
                for item in sets
                if item[side] > item[other_side]
            )
            wins[player_key].append({
                "opponent": opponent,
                "opponent_award": opponent_award,
                "straight_sets": int(set_wins == 2 and set_losses == 0),
                "winning_set_margin": winning_set_margin,
            })

    summaries = []
    for row in rankings:
        player_wins = wins.get(identity(row["name"]), [])
        first_wins = [item for item in player_wins if item["opponent_award"] == "Giải Nhất"]
        second_wins = [item for item in player_wins if item["opponent_award"] == "Giải Nhì"]
        third_wins = [item for item in player_wins if item["opponent_award"] == "Giải Ba"]

        if first_wins:
            priority = 1
            basis = first_wins
        elif len({identity(item["opponent"]) for item in second_wins}) >= 2:
            priority = 2
            basis = second_wins
        elif (
            len({identity(item["opponent"]) for item in second_wins}) >= 1
            and len({identity(item["opponent"]) for item in third_wins}) >= 2
        ):
            priority = 3
            basis = second_wins + third_wins
        else:
            continue

        summaries.append({
            "name": row["name"],
            "priority": priority,
            "priority_label": f"Ưu tiên {priority}",
            "basis_matches": len(basis),
            "straight_set_wins": sum(item["straight_sets"] for item in basis),
            "winning_set_margin": sum(item["winning_set_margin"] for item in basis),
            "opponents": [item["opponent"] for item in basis],
        })

    if not summaries:
        config.update({
            "status": "no_eligible", "recipients": [], "candidates": [],
            "note": "Chưa có tay vợt đáp ứng một trong ba mức ưu tiên của danh hiệu.",
            "rows": [],
        })
        return config

    active_priority = min(item["priority"] for item in summaries)
    eligible_rows = [item for item in summaries if item["priority"] == active_priority]
    eligible_rows.sort(key=lambda item: (
        -item["straight_set_wins"], -item["winning_set_margin"], item["name"].casefold(),
    ))
    config["rows"] = eligible_rows

    best = eligible_rows[0]
    tie_key = lambda item: (item["straight_set_wins"], item["winning_set_margin"])
    leaders = [item for item in eligible_rows if tie_key(item) == tie_key(best)]
    if len(leaders) > 1:
        config.update({
            "status": "tied_unawarded", "recipients": [], "candidates": leaders,
            "note": "Các tiêu chí phân định vẫn bằng nhau nên danh hiệu không được trao.",
        })
    else:
        config.update({
            "status": "winner", "recipients": [best], "candidates": [],
            "note": f"Đáp ứng {best['priority_label'].lower()} và dẫn đầu theo tiêu chí phân định.",
        })
    return config


def _waiting_attitude_item(config, note):
    item = dict(config)
    item.update({"status": "waiting", "recipients": [], "candidates": [], "note": note})
    return item


def _active_star_statistics(rankings, excluded, blocked=False, decided_name=None):
    config = dict(ATTITUDE_AWARDS[1])
    if blocked:
        return _waiting_attitude_item(config, "Chờ xác định danh hiệu đối đầu trước.")
    eligible = [
        row for row in rankings
        if identity(row["name"]) not in excluded and row["unofficial_completed"] >= 1
    ]
    eligible.sort(key=lambda row: (-row["stars"], -row["unofficial_completed"], row["name"].casefold()))
    if not eligible:
        config.update({
            "status": "no_eligible", "recipients": [], "candidates": [],
            "note": "Chưa có người hoàn thành trận không chính thức và được ghi nhận sao.",
        })
        return config
    best = eligible[0]
    leaders = [
        row for row in eligible
        if (row["stars"], row["unofficial_completed"]) == (best["stars"], best["unofficial_completed"])
    ]
    summaries = [
        {"name": row["name"], "stars": row["stars"], "matches": row["unofficial_completed"]}
        for row in leaders
    ]
    if len(leaders) > 1:
        decided = next(
            (item for item in summaries if identity(item["name"]) == identity(decided_name)), None
        ) if decided_name else None
        if decided:
            config.update({
                "status": "winner", "recipients": [decided], "candidates": [],
                "note": "Đã được Ban Tổ chức phân định trong nhóm bằng sao.",
            })
        else:
            config.update({
                "status": "draw", "recipients": [], "candidates": summaries,
                "note": "Bằng tổng sao và số trận không chính thức; BTC cần bốc thăm.",
            })
    else:
        config.update({
            "status": "winner", "recipients": summaries, "candidates": [],
            "note": "Có tổng sao cao nhất trong danh sách còn đủ điều kiện.",
        })
    return config


def _active_flower_statistics(contributors, excluded, blocked=False, decided_name=None):
    config = dict(ATTITUDE_AWARDS[2])
    if blocked:
        return _waiting_attitude_item(config, "Chờ xác định các danh hiệu thái độ trước.")
    eligible = [item for item in contributors if identity(item["name"]) not in excluded and item["flowers"] >= 1]
    if not eligible:
        config.update({
            "status": "no_eligible", "recipients": [], "candidates": [],
            "note": "Chưa có lượt trọng tài hợp lệ trong danh sách còn đủ điều kiện.",
        })
        return config
    top_flowers = max(item["flowers"] for item in eligible)
    leaders = [item for item in eligible if item["flowers"] == top_flowers]
    summaries = [{"name": item["name"], "flowers": item["flowers"]} for item in leaders]
    if len(leaders) > 1:
        decided = next(
            (item for item in summaries if identity(item["name"]) == identity(decided_name)), None
        ) if decided_name else None
        if decided:
            config.update({
                "status": "winner", "recipients": [decided], "candidates": [],
                "note": "Đã được Ban Tổ chức phân định trong nhóm bằng hoa.",
            })
        else:
            config.update({
                "status": "draw", "recipients": [], "candidates": summaries,
                "note": "Bằng tổng hoa; BTC cần bốc thăm công khai.",
            })
    else:
        config.update({
            "status": "winner", "recipients": summaries, "candidates": [],
            "note": "Có tổng hoa cao nhất trong danh sách còn đủ điều kiện.",
        })
    return config


def _build_draw_tasks(achievement, attitude, decisions):
    tasks = []
    second = next(item for item in achievement["items"] if item["key"] == "second")
    third = next(item for item in achievement["items"] if item["key"] == "third")
    if second["candidates"]:
        tasks.append({
            "key": "achievement_second",
            "title": "Ranh giới Giải Nhì và Giải Ba",
            "award_title": "Giải Nhì",
            "description": "Chọn người nhận suất Giải Nhì còn thiếu; những người còn lại được xét Giải Ba.",
            "slots": max(1, second["quantity"] - len(second["recipients"])),
            "candidates": second["candidates"],
            "selected": decisions.get("achievement_second", []),
        })
    elif third["candidates"]:
        tasks.append({
            "key": "achievement_third",
            "title": "Ranh giới cuối Giải Ba",
            "award_title": "Giải Ba",
            "description": "Bốc thăm để chọn đủ số suất Giải Ba còn lại.",
            "slots": max(1, third["quantity"] - len(third["recipients"])),
            "candidates": third["candidates"],
            "selected": decisions.get("achievement_third", []),
        })

    for item in attitude["items"]:
        if item["status"] == "draw":
            tasks.append({
                "key": item["key"],
                "title": item["title"],
                "award_title": item["title"],
                "description": item["note"],
                "slots": 1,
                "candidates": item["candidates"],
                "selected": decisions.get(item["key"]),
            })
            break
    return tasks


def calculate_awards(matches, rankings=None, contributors=None, *, locked=False, decisions=None):
    rankings = rankings if rankings is not None else calculate_rankings(matches)
    contributors = contributors if contributors is not None else calculate_contributors(matches)
    decisions = decisions or {}
    _apply_achievement_decisions(rankings, decisions)
    achievement = _achievement_statistics(rankings)

    head_to_head = _head_to_head_statistics(matches, rankings, achievement["resolved"])
    excluded = {identity(item["name"]) for item in head_to_head.get("recipients", [])}
    head_blocked = head_to_head["status"] == "waiting"

    active_star = _active_star_statistics(
        rankings, excluded, blocked=head_blocked, decided_name=decisions.get("active_star")
    )
    excluded.update(identity(item["name"]) for item in active_star.get("recipients", []))
    star_blocked = head_blocked or active_star["status"] in {"waiting", "draw"}

    active_flower = _active_flower_statistics(
        contributors, excluded, blocked=star_blocked, decided_name=decisions.get("active_flower")
    )
    attitude_items = [head_to_head, active_star, active_flower]
    attitude_allocated = sum(
        item["prize"] for item in attitude_items if item["status"] == "winner"
    )
    attitude = {
        "items": attitude_items,
        "budget": sum(item["prize"] for item in attitude_items),
        "allocated": attitude_allocated,
    }
    result = {
        "finalized": bool(locked),
        "status_label": "Chính thức" if locked else "Dự kiến",
        "total_budget": achievement["budget"] + attitude["budget"],
        "allocated": achievement["allocated"] + attitude_allocated,
        "achievement": achievement,
        "attitude": attitude,
        "decisions": decisions,
    }
    result["draws"] = _build_draw_tasks(achievement, attitude, decisions)
    return result


def summarize(matches, rankings):
    approved = [m for m in matches if m.get("status") == "approved"]
    return {
        "approved_matches": len(approved),
        "players": len(rankings),
        "pending_matches": sum(1 for m in matches if m.get("status") == "pending"),
        "flowers": sum(item["flowers"] for item in calculate_contributors(matches)),
    }
