from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from bson import ObjectId
from pymongo.errors import PyMongoError

from app import create_app


class Cursor:
    def __init__(self, items):
        self.items = list(items)

    def sort(self, fields):
        for field, direction in reversed(fields):
            self.items.sort(key=lambda item: item[field], reverse=direction == -1)
        return self

    def skip(self, count):
        self.items = self.items[count:]
        return self

    def limit(self, count):
        self.items = self.items[:count]
        return self

    def __iter__(self):
        return iter(self.items)


class Collection:
    def __init__(self):
        self.items = []

    def insert_one(self, document):
        document = {**document, "_id": ObjectId()}
        self.items.append(document)
        return SimpleNamespace(inserted_id=document["_id"])

    def find(self, query):
        return Cursor(item for item in self.items if all(item.get(key) == value for key, value in query.items()))

    def find_one(self, query):
        return next(iter(self.find(query)), None)

    def count_documents(self, query):
        return len(list(self.find(query)))


@pytest.fixture
def forum(monkeypatch):
    db = SimpleNamespace(forum_posts=Collection(), forum_comments=Collection())
    monkeypatch.setattr("app.routes.forum.get_db", lambda: db)
    app = create_app({"TESTING": True, "SECRET_KEY": "forum-tests"})
    client = app.test_client()
    client.get("/dien-dan")
    with client.session_transaction() as session:
        token = session["forum_csrf"]
    return client, db, token


def new_post(client, token, **overrides):
    return client.post("/dien-dan", data={"csrf_token": token, "author_name": "  Hùng  Nguyễn ",
                                          "title": "Hẹn ra sân", "content": "Tối nay ai chơi?", **overrides})


def test_post_and_comment_persist_and_display(forum):
    client, db, token = forum
    response = new_post(client, token)
    assert response.status_code == 303
    post = db.forum_posts.items[0]
    assert post["author_name"] == "Hùng Nguyễn"
    assert isinstance(post["created_at"], datetime)
    thread = response.headers["Location"]
    response = client.post(thread, data={"csrf_token": token, "author_name": "Lan", "content": "Mình tham gia!"})
    assert response.status_code == 303
    comment = db.forum_comments.items[0]
    assert comment["post_id"] == post["_id"]
    assert comment["author_name"] == "Lan"
    html = client.get(thread).get_data(as_text=True)
    assert "Tối nay ai chơi?" in html and "Mình tham gia!" in html
    assert "1 bình luận" in html


@pytest.mark.parametrize("field,value", [("author_name", "  "), ("title", ""), ("content", ""),
                                         ("author_name", "x" * 81), ("title", "x" * 161), ("content", "x" * 5001)])
def test_invalid_posts_are_not_saved(forum, field, value):
    client, db, token = forum
    response = new_post(client, token, **{field: value})
    assert response.status_code == 422
    assert not db.forum_posts.items


@pytest.mark.parametrize("name,content", [("", "Hi"), ("Lan", "  "), ("Lan", "x" * 2001)])
def test_invalid_comments_are_not_saved(forum, name, content):
    client, db, token = forum
    thread = new_post(client, token).headers["Location"]
    response = client.post(thread, data={"csrf_token": token, "author_name": name, "content": content})
    assert response.status_code == 422
    assert not db.forum_comments.items


def test_csrf_and_missing_post(forum):
    client, db, token = forum
    assert new_post(client, "").status_code == 400
    assert new_post(client, "không hợp lệ").status_code == 400
    assert not db.forum_posts.items
    assert client.get("/dien-dan/invalid").status_code == 404
    missing = f"/dien-dan/{ObjectId()}"
    assert client.get(missing).status_code == 404
    assert client.post(missing, data={"csrf_token": token, "author_name": "Lan", "content": "Hi"}).status_code == 404
    assert not db.forum_comments.items


def test_content_is_escaped_and_comments_stay_with_their_post(forum):
    client, db, token = forum
    first = new_post(client, token, content='<script>alert("x")</script>').headers["Location"]
    second = new_post(client, token, title="Bài thứ hai").headers["Location"]
    client.post(first, data={"csrf_token": token, "author_name": "<b>Lan</b>", "content": "Riêng bài một"})
    html = client.get(first).get_data(as_text=True)
    assert "<script>alert" not in html
    assert "&lt;script&gt;" in html and "&lt;b&gt;Lan&lt;/b&gt;" in html
    assert "Riêng bài một" not in client.get(second).get_data(as_text=True)


def test_pagination(forum):
    client, db, token = forum
    for index in range(21):
        db.forum_posts.insert_one({"author_name": "Lan", "title": f"Bài số {index:02}",
                                  "content": "Nội dung", "created_at": datetime(2026, 10, 13, 0, index, tzinfo=timezone.utc)})
    first = client.get("/dien-dan").get_data(as_text=True)
    second = client.get("/dien-dan?page=2").get_data(as_text=True)
    assert "Bài số 20" in first and "Bài số 00" not in first
    assert "Bài số 00" in second and "Bài số 20" not in second
    assert "Trang sau" in first and "Trang sau" not in second


def test_database_error_preserves_draft(forum, monkeypatch):
    client, db, token = forum
    def fail(*args):
        raise PyMongoError("Disconnected")
    monkeypatch.setattr(db.forum_posts, "insert_one", fail)
    response = new_post(client, token)
    assert response.status_code == 503
    assert "Tối nay ai chơi?" in response.get_data(as_text=True)
    assert not db.forum_posts.items


def test_comment_database_error_preserves_form(forum, monkeypatch):
    client, db, token = forum
    thread = new_post(client, token).headers["Location"]
    def fail(*args):
        raise PyMongoError("Disconnected")
    monkeypatch.setattr(db.forum_comments, "insert_one", fail)
    response = client.post(thread, data={"csrf_token": token, "author_name": "Lan", "content": "Giữ bản nháp"})
    assert response.status_code == 503
    assert "Giữ bản nháp" in response.get_data(as_text=True)
    assert not db.forum_comments.items
