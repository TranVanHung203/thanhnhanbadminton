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
        'content="https://badminton-thanhnhanteam.onrender.com/thanh-nhan-social-preview-v2.png"'
        in html
    )
    assert (
        'property="og:url" '
        'content="https://badminton-thanhnhanteam.onrender.com/nhap-ket-qua"'
        in html
    )
    assert 'property="og:image:width" content="1733"' in html
    assert 'property="og:image:height" content="908"' in html
    assert 'name="twitter:card" content="summary_large_image"' in html


def test_social_preview_image_is_public():
    app = create_app({"TESTING": True})

    with app.test_client() as client:
        response = client.get("/thanh-nhan-social-preview-v2.png")

    assert response.status_code == 200
    assert response.content_type == "image/png"
    assert len(response.data) > 100_000
