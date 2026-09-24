from app.services.validation import match_winner, valid_set_score, validate_match_payload


def base_payload():
    return {
        "month": "2026-09",
        "played_date": "2026-09-20",
        "played_time": "14:00",
        "stage": "group",
        "player_a": "Nguyễn Văn A",
        "player_b": "Trần Văn B",
        "referee_1": "Lê Văn C",
        "referee_2": "Phạm Văn D",
        "result_status": "completed",
        "set1_a": 15,
        "set1_b": 12,
        "set2_a": 13,
        "set2_b": 15,
        "set3_a": 17,
        "set3_b": 15,
        "evidence_urls": ["https://drive.google.com/example"],
        "voluntary_confirmed": True,
        "referees_confirmed": True,
        "photo_before_confirmed": True,
        "rules_confirmed": True,
        "score_confirmed": True,
        "photo_after_confirmed": True,
        "submitted_by_referee": True,
    }


def test_legal_scores():
    assert valid_set_score(15, 0)
    assert valid_set_score(16, 14)
    assert valid_set_score(17, 16)
    assert not valid_set_score(15, 14)
    assert not valid_set_score(18, 16)


def test_valid_completed_match():
    cleaned, errors = validate_match_payload(base_payload())
    assert errors == {}
    assert match_winner(cleaned["sets"]) == "a"


def test_rejects_duplicate_roles_and_wrong_stage_date():
    payload = base_payload()
    payload["referee_1"] = payload["player_a"]
    payload["played_date"] = "2026-09-25"
    _, errors = validate_match_payload(payload)
    assert "roles" in errors
    assert "played_date" in errors


def test_rejects_unnecessary_third_set():
    payload = base_payload()
    payload.update({"set1_a": 15, "set1_b": 9, "set2_a": 15, "set2_b": 8, "set3_a": 15, "set3_b": 7})
    _, errors = validate_match_payload(payload)
    assert "sets" in errors

