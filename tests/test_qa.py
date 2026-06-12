import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from datetime import datetime

from app.modules.qa.schemas import (
    AskInput, AskOutput, ConversationResponse, MessageResponse,
    ConversationCreate, FeedbackInput,
)
from app.modules.qa.router import router
from app.main import app


class TestQAEndpoints:
    def test_ask_requires_auth(self, client):
        response = client.post("/api/v1/qa/ask", json={
            "question": "什么是二叉树？",
        })
        assert response.status_code in [401, 403]

    def test_ask_invalid_input(self, client, override_get_db, override_get_current_user):
        response = client.post("/api/v1/qa/ask", json={
            "question": "",
        })
        assert response.status_code == 422

    def test_ask_question_too_long(self, client, override_get_db, override_get_current_user):
        response = client.post("/api/v1/qa/ask", json={
            "question": "a" * 50001,
        })
        assert response.status_code == 422

    def test_list_conversations(self, authed_client, mock_db):
        mock_db.query.return_value.filter.return_value \
            .order_by.return_value.offset.return_value \
            .limit.return_value.all.return_value = []
        mock_db.query.return_value.filter.return_value.count.return_value = 0
        response = authed_client.get("/api/v1/qa/conversations")
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200
        assert "items" in data["data"]

    def test_list_conversations_pagination(self, authed_client, mock_db):
        mock_db.query.return_value.filter.return_value \
            .order_by.return_value.offset.return_value \
            .limit.return_value.all.return_value = []
        mock_db.query.return_value.filter.return_value.count.return_value = 5
        response = authed_client.get("/api/v1/qa/conversations?page=2&size=10")
        assert response.status_code == 200

    def test_get_conversation_messages(self, authed_client, mock_db):
        mock_db.query.return_value.filter.return_value.first.return_value = None
        with patch("app.modules.qa.router.QaService.get_messages") as mock_get:
            mock_get.return_value = (None, [])
            response = authed_client.get("/api/v1/qa/conversations/999/messages")
            assert response.status_code == 404

    def test_get_messages_success(self, authed_client, mock_db):
        from tests.conftest import MockConversation, MockMessage
        mock_conv = MockConversation()
        mock_msg = MockMessage()

        with patch("app.modules.qa.router.QaService.get_messages") as mock_get:
            mock_get.return_value = (mock_conv, [mock_msg])
            response = authed_client.get("/api/v1/qa/conversations/1/messages")
            assert response.status_code == 200

    def test_delete_conversation_not_found(self, authed_client, mock_db):
        with patch("app.modules.qa.router.QaService.delete_conversation") as mock_del:
            mock_del.return_value = False
            response = authed_client.delete("/api/v1/qa/conversations/999")
            assert response.status_code == 404

    def test_delete_conversation_success(self, authed_client, mock_db):
        with patch("app.modules.qa.router.QaService.delete_conversation") as mock_del:
            mock_del.return_value = True
            response = authed_client.delete("/api/v1/qa/conversations/1")
            assert response.status_code == 200

    def test_submit_feedback_not_found(self, authed_client, mock_db):
        with patch("app.modules.qa.router.QaService.submit_feedback") as mock_fb:
            mock_fb.return_value = None
            response = authed_client.post("/api/v1/qa/feedback/999",
                                          json={"score": 4})
            assert response.status_code == 404

    def test_submit_feedback_success(self, authed_client, mock_db):
        from tests.conftest import MockMessage
        with patch("app.modules.qa.router.QaService.submit_feedback") as mock_fb:
            mock_fb.return_value = MockMessage()
            response = authed_client.post("/api/v1/qa/feedback/1",
                                          json={"score": 4})
            assert response.status_code == 200

    def test_feedback_score_range(self, authed_client):
        response = authed_client.post("/api/v1/qa/feedback/1",
                                      json={"score": 6})
        assert response.status_code == 422

    def test_feedback_score_min(self, authed_client):
        response = authed_client.post("/api/v1/qa/feedback/1",
                                      json={"score": 0})
        assert response.status_code == 422

    def test_feedback_add_to_wrong_q(self, authed_client, mock_db, mock_normal_user):
        from tests.conftest import MockMessage, MockConversation
        mock_normal_user.role = "user"

        mock_db.query.return_value.filter.return_value.first.return_value = MockConversation(subject_id=1)
        mock_db.query.return_value.filter.return_value.order_by.return_value.first.return_value = MockMessage(content="真实的问题内容")

        with patch("app.modules.qa.router.QaService.submit_feedback") as mock_fb:
            mock_fb.return_value = MockMessage(conversation_id=1)
            with patch("app.modules.qa.router.WrongQService.create") as mock_wq:
                mock_wq.return_value = MagicMock()
                response = authed_client.post("/api/v1/qa/feedback/1", json={
                    "score": 2,
                    "add_to_wrong": True,
                    "correct_answer": "A",
                    "user_answer": "B",
                    "error_reason": "misunderstanding",
                })
                assert response.status_code == 200


class TestQASchemas:
    def test_ask_input_conversation_id(self):
        input_data = AskInput(question="test", conversation_id=5, subject_id=3)
        assert input_data.conversation_id == 5
        assert input_data.subject_id == 3

    def test_ask_output_model_dump(self):
        output = AskOutput(conversation_id=1, message_id=1,
                           answer="answer", sources=[{"doc": "test"}])
        data = output.model_dump()
        assert data["conversation_id"] == 1
        assert len(data["sources"]) == 1

    def test_conversation_create(self):
        conv = ConversationCreate(subject_id=1, title="新对话")
        assert conv.title == "新对话"

    def test_conversation_response_serialization(self):
        from tests.conftest import MockConversation
        conv = MockConversation(subject_id=3)
        resp = ConversationResponse.model_validate(conv)
        data = resp.model_dump()
        assert data["subject_id"] == 3
        assert data["title"] == "测试对话"

    def test_message_response_with_sources(self):
        from tests.conftest import MockMessage
        msg = MockMessage(sources=[{"doc_id": 1, "content": "test"}])
        resp = MessageResponse.model_validate(msg)
        assert len(resp.sources) == 1

    def test_feedback_input_defaults(self):
        fb = FeedbackInput(score=3)
        assert fb.add_to_wrong is False
        assert fb.correct_answer is None
