from datetime import datetime

import pytest
from unittest.mock import MagicMock, patch

from app.modules.notes.schemas import (
    NoteCreate, NoteUpdate, NoteResponse, CommentCreate, CommentResponse,
    ReviewInput, BatchReviewInput, AiReviewResponse,
)


class MockNote:
    def __init__(self, id=1, user_id=1, subject_id=1, title="title", content="content",
                 tags=None, status="published", reject_reason=None, is_pinned=0,
                 like_count=0, favorite_count=0, comment_count=0,
                 created_at=None, updated_at=None, username="testuser"):
        self.id = id
        self.user_id = user_id
        self.subject_id = subject_id
        self.title = title
        self.content = content
        self.tags = tags or []
        self.status = status
        self.reject_reason = reject_reason
        self.is_pinned = is_pinned
        self.like_count = like_count
        self.favorite_count = favorite_count
        self.comment_count = comment_count
        self.created_at = created_at or datetime.now()
        self.updated_at = updated_at or datetime.now()
        self.username = username


class MockComment:
    def __init__(self, id=1, note_id=1, user_id=1, content="content",
                 created_at=None, username="testuser"):
        self.id = id
        self.note_id = note_id
        self.user_id = user_id
        self.content = content
        self.created_at = created_at or datetime.now()
        self.username = username


class TestNotesEndpoints:
    def test_list_notes_requires_auth(self, client):
        response = client.get("/api/v1/notes")
        assert response.status_code == 403

    def test_list_notes_success(self, authed_client, mock_db):
        with patch("app.modules.notes.router.NotesService.list_notes") as mock_list:
            mock_list.return_value = ([], 0)
            response = authed_client.get("/api/v1/notes")
            assert response.status_code == 200

    def test_list_notes_with_filters(self, authed_client, mock_db):
        with patch("app.modules.notes.router.NotesService.list_notes") as mock_list:
            mock_list.return_value = ([], 0)
            response = authed_client.get("/api/v1/notes?subject_id=1&keyword=测试")
            assert response.status_code == 200

    def test_get_note_not_found(self, authed_client, mock_db):
        with patch("app.modules.notes.router.NotesService.get_note") as mock_get:
            mock_get.return_value = None
            response = authed_client.get("/api/v1/notes/999")
            assert response.status_code == 404

    def test_get_note_success(self, authed_client, mock_db):
        with patch("app.modules.notes.router.NotesService.get_note") as mock_get:
            mock_get.return_value = MockNote(
                id=1, user_id=2, subject_id=1, title="心得",
                content="内容", tags=["算法"], status="published",
                reject_reason=None, is_pinned=0, like_count=5,
                favorite_count=2, comment_count=1, username="student",
            )
            response = authed_client.get("/api/v1/notes/1")
            assert response.status_code == 200

    def test_get_note_unpublished_not_owner(self, authed_client, mock_db):
        with patch("app.modules.notes.router.NotesService.get_note") as mock_get:
            mock_get.return_value = MockNote(
                id=1, user_id=999, status="pending",
            )
            response = authed_client.get("/api/v1/notes/1")
            assert response.status_code == 403

    def test_create_note_success(self, authed_client, mock_db):
        with patch("app.modules.notes.router.NotesService.create_note") as mock_create:
            mock_create.return_value = MockNote(
                id=1, user_id=2, subject_id=1, title="新心得",
                content="内容", tags=None, status="pending",
                reject_reason=None, is_pinned=0, like_count=0,
                favorite_count=0, comment_count=0, username="student",
            )
            response = authed_client.post("/api/v1/notes", json={
                "subject_id": 1, "title": "新心得", "content": "心得体会内容",
            })
            assert response.status_code == 200

    def test_create_note_admin_forbidden(self, admin_client):
        response = admin_client.post("/api/v1/notes", json={
            "subject_id": 1, "title": "test", "content": "content",
        })
        assert response.status_code == 403

    def test_create_note_empty_content(self, authed_client):
        response = authed_client.post("/api/v1/notes", json={
            "subject_id": 1, "title": "标题", "content": "",
        })
        assert response.status_code == 422

    def test_update_note_not_found(self, authed_client, mock_db):
        with patch("app.modules.notes.router.NotesService.update_note") as mock_upd:
            mock_upd.return_value = None
            response = authed_client.put("/api/v1/notes/999",
                                         json={"title": "新标题"})
            assert response.status_code == 404

    def test_delete_note_success(self, authed_client, mock_db):
        with patch("app.modules.notes.router.NotesService.delete_note") as mock_del:
            mock_del.return_value = True
            response = authed_client.delete("/api/v1/notes/1")
            assert response.status_code == 200

    def test_toggle_like_success(self, authed_client, mock_db):
        with patch("app.modules.notes.router.NotesService.toggle_field") as mock_tog:
            mock_tog.return_value = ("added", 1)
            response = authed_client.post("/api/v1/notes/1/like")
            assert response.status_code == 200
            assert response.json()["data"]["liked"] is True

    def test_toggle_like_not_found(self, authed_client, mock_db):
        with patch("app.modules.notes.router.NotesService.toggle_field") as mock_tog:
            mock_tog.return_value = (None, 0)
            response = authed_client.post("/api/v1/notes/999/like")
            assert response.status_code == 404

    def test_toggle_favorite(self, authed_client, mock_db):
        with patch("app.modules.notes.router.NotesService.toggle_field") as mock_tog:
            mock_tog.return_value = ("removed", 5)
            response = authed_client.post("/api/v1/notes/1/favorite")
            assert response.status_code == 200
            assert response.json()["data"]["favorited"] is False

    def test_get_comments(self, authed_client, mock_db):
        with patch("app.modules.notes.router.NotesService.get_comments") as mock_c:
            mock_c.return_value = []
            response = authed_client.get("/api/v1/notes/1/comments")
            assert response.status_code == 200

    def test_add_comment_success(self, authed_client, mock_db):
        with patch("app.modules.notes.router.NotesService.add_comment") as mock_add:
            mock_add.return_value = MockComment(
                id=1, note_id=1, user_id=2, content="好文章",
                username="student",
            )
            response = authed_client.post("/api/v1/notes/1/comments",
                                          json={"content": "好文章"})
            assert response.status_code == 200

    def test_add_comment_not_found(self, authed_client, mock_db):
        with patch("app.modules.notes.router.NotesService.add_comment") as mock_add:
            mock_add.return_value = None
            response = authed_client.post("/api/v1/notes/999/comments",
                                          json={"content": "test"})
            assert response.status_code == 404

    def test_get_my_counts(self, authed_client, mock_db):
        with patch("app.modules.notes.router.NotesService.get_my_counts") as mock_c:
            mock_c.return_value = {"published": 5, "pending": 2, "rejected": 1}
            response = authed_client.get("/api/v1/notes/my-counts")
            assert response.status_code == 200

    # Admin endpoints
    def test_list_review_non_admin(self, authed_client):
        response = authed_client.get("/api/v1/notes/admin/review")
        assert response.status_code == 403

    def test_list_review_as_admin(self, admin_client, mock_db):
        with patch("app.modules.notes.router.NotesService.list_notes") as mock_list:
            mock_list.return_value = ([], 0)
            response = admin_client.get("/api/v1/notes/admin/review")
            assert response.status_code == 200

    def test_review_note_as_admin(self, admin_client, mock_db):
        with patch("app.modules.notes.router.NotesService.review_note") as mock_rev:
            mock_rev.return_value = MockNote(
                id=1, user_id=2, subject_id=1, title="t", content="c",
                tags=None, status="published", reject_reason=None,
                is_pinned=0, like_count=0, favorite_count=0, comment_count=0,
                username="student",
            )
            response = admin_client.post("/api/v1/notes/admin/review/1",
                                         json={"action": "approve"})
            assert response.status_code == 200

    def test_batch_review_as_admin(self, admin_client, mock_db):
        with patch("app.modules.notes.router.NotesService.batch_review") as mock_br:
            mock_br.return_value = {"approved": 2, "rejected": 0}
            response = admin_client.post("/api/v1/notes/admin/review/batch",
                                         json={"ids": [1, 2], "action": "approve"})
            assert response.status_code == 200

    def test_toggle_pin_as_admin(self, admin_client, mock_db):
        with patch("app.modules.notes.router.NotesService.toggle_pin") as mock_pin:
            mock_pin.return_value = MockNote(
                id=1, user_id=2, subject_id=1, title="t", content="c",
                tags=None, status="published", reject_reason=None,
                is_pinned=1, like_count=0, favorite_count=0, comment_count=0,
                username="student",
            )
            response = admin_client.post("/api/v1/notes/admin/pin/1")
            assert response.status_code == 200


class TestNotesSchemas:
    def test_note_create_with_tags(self):
        note = NoteCreate(subject_id=1, title="标题", content="内容",
                          tags=["数据结构", "算法"])
        assert len(note.tags) == 2

    def test_note_update_partial(self):
        update = NoteUpdate(title="新标题")
        assert update.title == "新标题"
        assert update.content is None

    def test_comment_create_max_length(self):
        with pytest.raises(Exception):
            CommentCreate(content="a" * 2001)

    def test_review_input_approve(self):
        review = ReviewInput(action="approve")
        assert review.action == "approve"

    def test_review_input_reject(self):
        review = ReviewInput(action="reject", reject_reason="质量低")
        assert review.reject_reason == "质量低"

    def test_batch_review_input_max_ids(self):
        with pytest.raises(Exception):
            BatchReviewInput(ids=list(range(101)), action="approve")

    def test_ai_review_response(self):
        resp = AiReviewResponse(
            suggested_action="approve", confidence=0.85,
            reasons=["内容充实"], quality_score=8, summary="优秀",
        )
        assert resp.suggested_action == "approve"
        assert resp.quality_score == 8
