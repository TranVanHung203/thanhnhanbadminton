import re
from datetime import datetime
from urllib.parse import urlparse


YES_FIELDS = (
    "voluntary_confirmed",
    "referees_confirmed",
    "photo_before_confirmed",
    "rules_confirmed",
    "score_confirmed",
    "photo_after_confirmed",
    "submitted_by_referee",
)


def clean_name(value):
    return re.sub(r"\s+", " ", (value or "").strip())


def identity(value):
    return clean_name(value).casefold()


def parse_bool(value):
    return str(value).lower() in {"1", "true", "yes", "on", "có"}


def valid_set_score(a, b):
    if not isinstance(a, int) or not isinstance(b, int) or a < 0 or b < 0 or a == b:
        return False
    high, low = max(a, b), min(a, b)
    if high < 15 or high > 17:
        return False
    if high == 15:
        return low <= 13
    if high == 16:
        return low == 14
    return low in {15, 16}


def match_winner(sets):
    wins_a = sum(1 for item in sets if item["a"] > item["b"])
    wins_b = sum(1 for item in sets if item["b"] > item["a"])
    if wins_a == 2 and wins_b < 2:
        return "a"
    if wins_b == 2 and wins_a < 2:
        return "b"
    return None


def validate_match_payload(data, *, require_confirmations=True):
    errors = {}
    player_a = clean_name(data.get("player_a"))
    player_b = clean_name(data.get("player_b"))
    referee_1 = clean_name(data.get("referee_1"))
    referee_2 = clean_name(data.get("referee_2"))
    roles = [player_a, player_b, referee_1, referee_2]

    if any(not name for name in roles):
        errors["roles"] = "Cần nhập đủ 2 vận động viên và 2 trọng tài."
    elif len({identity(name) for name in roles}) != 4:
        errors["roles"] = "Một người không thể giữ hai vai trò trong cùng trận."

    month = str(data.get("month", ""))
    try:
        datetime.strptime(month, "%Y-%m")
    except ValueError:
        errors["month"] = "Tháng thi đấu không hợp lệ."

    played_date = str(data.get("played_date", ""))
    try:
        played = datetime.strptime(played_date, "%Y-%m-%d")
        if month and played.strftime("%Y-%m") != month:
            errors["played_date"] = "Ngày thi đấu phải thuộc tháng đã chọn."
        stage = data.get("stage")
        if stage == "group" and played.day > 21:
            errors["played_date"] = "Vòng bảng chỉ nhận trận từ ngày 1 đến ngày 21."
        if stage == "final" and played.day < 22:
            errors["played_date"] = "Vòng phân hạng bắt đầu từ ngày 22."
    except ValueError:
        errors["played_date"] = "Ngày thi đấu không hợp lệ."

    if data.get("stage") not in {"group", "final"}:
        errors["stage"] = "Giai đoạn không hợp lệ."

    result_status = data.get("result_status", "completed")
    if result_status not in {"completed", "forfeit", "paused"}:
        errors["result_status"] = "Trạng thái trận không hợp lệ."

    sets = []
    if result_status == "completed":
        for number in (1, 2, 3):
            raw_a, raw_b = data.get(f"set{number}_a"), data.get(f"set{number}_b")
            if raw_a in (None, "") and raw_b in (None, ""):
                continue
            try:
                a, b = int(raw_a), int(raw_b)
            except (TypeError, ValueError):
                errors["sets"] = "Tỷ số set phải là số nguyên."
                continue
            if not valid_set_score(a, b):
                errors["sets"] = f"Tỷ số set {number} chưa đúng luật 15 điểm, trần 17."
            sets.append({"a": a, "b": b})
        if len(sets) not in {2, 3} or match_winner(sets) is None:
            errors["sets"] = "Trận hoàn thành phải có người thắng đủ 2 set; set 3 chỉ dùng khi hòa 1–1."
        elif len(sets) == 3 and ((sets[0]["a"] > sets[0]["b"]) == (sets[1]["a"] > sets[1]["b"])):
            errors["sets"] = "Không thi đấu set 3 khi một bên đã thắng hai set đầu."
    elif result_status == "forfeit":
        if data.get("forfeit_side") not in {"a", "b"}:
            errors["forfeit_side"] = "Cần chọn người bỏ cuộc."

    evidence = []
    for url in data.get("evidence_urls", []) if isinstance(data.get("evidence_urls"), list) else str(data.get("evidence_urls", "")).splitlines():
        url = url.strip()
        if not url:
            continue
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            errors["evidence_urls"] = "Mỗi minh chứng phải là một đường dẫn http/https hợp lệ."
        else:
            evidence.append(url)

    confirmations = {key: parse_bool(data.get(key)) for key in YES_FIELDS}
    if require_confirmations and not all(confirmations.values()):
        errors["confirmations"] = "Cần xác nhận đủ các điều kiện công nhận trận đấu."

    cleaned = {
        "month": month,
        "played_date": played_date,
        "played_time": str(data.get("played_time", "")).strip(),
        "stage": data.get("stage"),
        "player_a": player_a,
        "player_b": player_b,
        "referee_1": referee_1,
        "referee_2": referee_2,
        "sets": sets,
        "result_status": result_status,
        "forfeit_side": data.get("forfeit_side") if result_status == "forfeit" else None,
        "forfeit_reason_valid": parse_bool(data.get("forfeit_reason_valid")),
        "confirmations": confirmations,
        "evidence_urls": evidence,
        "notes": str(data.get("notes", "")).strip(),
    }
    return cleaned, errors

