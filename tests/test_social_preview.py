from flask import render_template

from app import create_app


def test_submit_page_has_absolute_social_preview_metadata():
    app = create_app({"TESTING": True})

    with app.test_request_context(
        "/nhap-ket-qua",
        base_url="https://badminton-thanhnhanteam.onrender.com",
    ):
        html = render_template(
            "submit.html",
            month="2026-09",
            meta_title="Nhập kết quả thi đấu · Thành Nhân Badminton",
            meta_description="Gửi kết quả và ảnh minh chứng trận đấu.",
        )

    assert 'property="og:title" content="Nhập kết quả thi đấu · Thành Nhân Badminton"' in html
    assert (
        'property="og:image" '
        'content="https://badminton-thanhnhanteam.onrender.com/thanh-nhan-logo.png"'
        in html
    )
    assert (
        'property="og:url" '
        'content="https://badminton-thanhnhanteam.onrender.com/nhap-ket-qua"'
        in html
    )
    assert 'name="twitter:card" content="summary"' in html
