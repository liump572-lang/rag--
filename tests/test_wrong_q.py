import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime

from app.modules.wrong_q.schemas import (
    WrongQuestionCreate, WrongQuestionUpdate, WrongQuestionResponse,
    ReviewInput, StatsOutput,
)


class TestWrongQEndpoints:
    def test_list_wq_requires_auth(self, client):
        response = client.get("/api/v1/wq")
        assert response.status_code == 403

    def test_list_wq_admin_forbidden(self, admin_client):
        response = admin_client.get("/api/v1/wq")
        assert response.status_code == 403

    def test_list_wq_success(self, authed_client, mock_db):
        mock_db.query.return_value.filter.return_value \
            .filter.return_value.order_by.return_value \
            .offset.return_value.limit.return_value \
            .all.return_value = []
        mock_db.query.return_value.filter.return_value \
            .filter.return_value.count.return_value = 0
        response = authed_client.get("/api/v1/wq")
        assert response.status_code == 200

    def test_list_wq_with_filters(self, authed_client, mock_db):
        with patch("app.modules.wrong_q.router.WrongQService.list") as mock_list:
            mock_list.return_value = ([], 0)
            response = authed_client.get(
                "/api/v1/wq?subject_id=1&mastery_status=pending&error_reason=careless"
            )
            assert response.status_code == 200

    def test_create_wq_success(self, authed_client, mock_db):
        with patch("app.modules.wrong_q.router.WrongQService.create") as mock_create:
            mock_create.return_value = MagicMock(
                id=1, user_id=2, subject_id=1,
                question_content="1+1=?", correct_answer="2",
                user_answer="3", error_reason="careless",
                difficulty=3, mastery_status="pending",
                review_count=0, mastered_at=None,
                created_at=datetime.now(), updated_at=datetime.now(),
            )
            response = authed_client.post("/api/v1/wq", json={
                "subject_id": 1,
                "question_content": "1+1=?",
                "correct_answer": "2",
                "user_answer": "3",
                "error_reason": "careless",
            })
            assert response.status_code == 200

    def test_create_wq_missing_required(self, authed_client):
        response = authed_client.post("/api/v1/wq", json={
            "question_content": "1+1=?",
        })
        assert response.status_code == 422

    def test_get_wq_not_found(self, authed_client, mock_db):
        with patch("app.modules.wrong_q.router.WrongQService.get") as mock_get:
            mock_get.return_value = None
            response = authed_client.get("/api/v1/wq/999")
            assert response.status_code == 404

    def test_get_wq_success(self, authed_client, mock_db):
        with patch("app.modules.wrong_q.router.WrongQService.get") as mock_get:
            mock_get.return_value = MagicMock(
                id=1, user_id=2, subject_id=1,
                question_content="1+1=?", correct_answer="2",
                user_answer="3", error_reason="careless",
                difficulty=3, mastery_status="pending",
                review_count=0, mastered_at=None,
                created_at=datetime.now(), updated_at=datetime.now(),
            )
            response = authed_client.get("/api/v1/wq/1")
            assert response.status_code == 200

    def test_update_wq_not_found(self, authed_client, mock_db):
        with patch("app.modules.wrong_q.router.WrongQService.update") as mock_upd:
            mock_upd.return_value = None
            response = authed_client.put("/api/v1/wq/999",
                                         json={"mastery_status": "mastered"})
            assert response.status_code == 404

    def test_update_wq_success(self, authed_client, mock_db):
        with patch("app.modules.wrong_q.router.WrongQService.update") as mock_upd:
            mock_upd.return_value = MagicMock(
                id=1, user_id=2, subject_id=1,
                question_content="q", correct_answer="a",
                user_answer="b", error_reason="careless",
                difficulty=3, mastery_status="mastered",
                review_count=1, mastered_at=None,
                created_at=datetime.now(), updated_at=datetime.now(),
            )
            response = authed_client.put("/api/v1/wq/1",
                                         json={"mastery_status": "mastered"})
            assert response.status_code == 200

    def test_delete_wq_not_found(self, authed_client, mock_db):
        with patch("app.modules.wrong_q.router.WrongQService.delete") as mock_del:
            mock_del.return_value = False
            response = authed_client.delete("/api/v1/wq/999")
            assert response.status_code == 404

    def test_delete_wq_success(self, authed_client, mock_db):
        with patch("app.modules.wrong_q.router.WrongQService.delete") as mock_del:
            mock_del.return_value = True
            response = authed_client.delete("/api/v1/wq/1")
            assert response.status_code == 200

    def test_get_stats(self, authed_client, mock_db):
        with patch("app.modules.wrong_q.router.WrongQService.stats") as mock_stats:
            mock_stats.return_value = {
                "total": 10, "by_subject": [], "by_reason": [], "by_status": [],
            }
            response = authed_client.get("/api/v1/wq/stats")
            assert response.status_code == 200

    def test_get_practice(self, authed_client, mock_db):
        with patch("app.modules.wrong_q.router.WrongQService.practice") as mock_prac:
            mock_prac.return_value = []
            response = authed_client.get("/api/v1/wq/practice?count=5")
            assert response.status_code == 200

    def test_review_wq_not_found(self, authed_client, mock_db):
        with patch("app.modules.wrong_q.router.WrongQService.review") as mock_rev:
            mock_rev.return_value = None
            response = authed_client.post("/api/v1/wq/999/review",
                                          json={"is_correct": True})
            assert response.status_code == 404

    def test_review_wq_success(self, authed_client, mock_db):
        with patch("app.modules.wrong_q.router.WrongQService.review") as mock_rev:
            mock_rev.return_value = MagicMock(
                id=1, user_id=2, subject_id=1,
                question_content="q", correct_answer="a",
                user_answer="b", error_reason="careless",
                difficulty=3, mastery_status="mastered",
                review_count=1, mastered_at=None,
                created_at=datetime.now(), updated_at=datetime.now(),
            )
            response = authed_client.post("/api/v1/wq/1/review",
                                          json={"is_correct": True,
                                                "mastery_status": "mastered"})
            assert response.status_code == 200


class TestWrongQSchemas:
    def test_wrong_q_create_all_fields(self):
        wq = WrongQuestionCreate(
            subject_id=1, question_content="1+1=?",
            correct_answer="2", user_answer="3",
            error_reason="knowledge_gap", difficulty=4,
        )
        assert wq.error_reason == "knowledge_gap"

    def test_wrong_q_update_mastery_status(self):
        update = WrongQuestionUpdate(mastery_status="mastered")
        assert update.mastery_status == "mastered"

    def test_wrong_q_response_from_orm(self):
        wq = MagicMock(
            id=1, user_id=2, subject_id=1,
            question_content="q", correct_answer="a",
            user_answer="b", error_reason="careless",
            difficulty=3, mastery_status="pending",
            review_count=0, mastered_at=None,
            created_at=datetime.now(), updated_at=datetime.now(),
        )
        resp = WrongQuestionResponse.model_validate(wq)
        assert resp.error_reason == "careless"
        assert resp.mastery_status == "pending"

    def test_review_input_defaults(self):
        review = ReviewInput(is_correct=True)
        assert review.is_correct is True
        assert review.mastery_status is None

    def test_stats_output(self):
        stats = StatsOutput(
            total=5, by_subject=[{"id": 1, "count": 3}],
            by_reason=[{"reason": "careless", "count": 2}],
            by_status=[{"status": "mastered", "count": 1}],
        )
        assert stats.total == 5
