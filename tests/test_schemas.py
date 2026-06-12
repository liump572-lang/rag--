import pytest
from datetime import datetime
from pydantic import ValidationError

from app.modules.qa.schemas import (
    AskInput, AskOutput, ConversationResponse, MessageResponse,
    ConversationCreate, FeedbackInput,
)
from app.modules.auth.schemas import (
    LoginInput, RegisterInput, RefreshInput, UserInfo, TokenOutput,
)
from app.modules.kb.schemas import (
    DocumentCreate, DocumentUpdate, DocumentResponse, DocumentFilter,
)
from app.modules.kg.schemas import (
    KnowledgePointCreate, KnowledgePointUpdate, KnowledgePointResponse,
    RelationCreate, RelationUpdate, RelationResponse,
    DocumentGenerateRequest,
)
from app.modules.notes.schemas import (
    NoteCreate, NoteUpdate, NoteResponse, CommentCreate, CommentResponse,
    ReviewInput, BatchReviewInput, AiReviewResponse,
)
from app.modules.wrong_q.schemas import (
    WrongQuestionCreate, WrongQuestionUpdate, WrongQuestionResponse,
    ReviewInput as WqReviewInput, StatsOutput,
)
from app.modules.notification.schemas import NotificationResponse
from app.modules.system.schemas import SettingsUpdate, KgExtractionSettings


# ==================== QA Schemas ====================

class TestAskInput:
    def test_valid_input(self):
        obj = AskInput(question="什么是二叉树？")
        assert obj.question == "什么是二叉树？"
        assert obj.conversation_id is None
        assert obj.subject_id is None

    def test_with_optional_fields(self):
        obj = AskInput(question="排序算法有哪些？", conversation_id=1, subject_id=2)
        assert obj.conversation_id == 1
        assert obj.subject_id == 2

    def test_max_length_boundary(self):
        text = "a" * 50000
        obj = AskInput(question=text)
        assert len(obj.question) == 50000

    def test_exceeds_max_length(self):
        with pytest.raises(ValidationError):
            AskInput(question="a" * 50001)

    def test_empty_question(self):
        with pytest.raises(ValidationError):
            AskInput(question="")

    def test_min_length(self):
        obj = AskInput(question="a")
        assert obj.question == "a"

    def test_conversation_id_none(self):
        obj = AskInput(question="test", conversation_id=None)
        assert obj.conversation_id is None


class TestAskOutput:
    def test_valid_output(self):
        obj = AskOutput(conversation_id=1, message_id=1, answer="这是答案")
        assert obj.conversation_id == 1
        assert obj.answer == "这是答案"
        assert obj.sources == []

    def test_with_sources(self):
        sources = [{"title": "文档1", "content": "内容"}]
        obj = AskOutput(conversation_id=1, message_id=1, answer="答案",
                        sources=sources)
        assert len(obj.sources) == 1


class TestConversationResponse:
    def test_valid_response(self):
        obj = ConversationResponse(
            id=1, title="测试", message_count=3, subject_id=2,
            created_at=datetime.now(), updated_at=datetime.now(),
        )
        assert obj.subject_id == 2

    def test_subject_id_optional(self):
        obj = ConversationResponse(
            id=1, title="测试", message_count=0,
            created_at=datetime.now(), updated_at=datetime.now(),
        )
        assert obj.subject_id is None

    def test_from_attributes(self):
        class MockConv:
            id = 1
            title = "test"
            message_count = 5
            subject_id = 2
            created_at = datetime.now()
            updated_at = datetime.now()

        resp = ConversationResponse.model_validate(MockConv())
        assert resp.subject_id == 2


class TestMessageResponse:
    def test_valid_message(self):
        obj = MessageResponse(
            id=1, role="user", content="你好", sources=None,
            question_type="knowledge", feedback_score=None,
            created_at=datetime.now(),
        )
        assert obj.role == "user"
        assert obj.content == "你好"

    def test_feedback_score(self):
        obj = MessageResponse(
            id=1, role="assistant", content="答案",
            feedback_score=4, created_at=datetime.now(),
        )
        assert obj.feedback_score == 4

    def test_from_attributes(self):
        class MockMsg:
            id = 1
            role = "assistant"
            content = "test"
            sources = [{"doc_id": 1}]
            question_type = "exam"
            feedback_score = None
            created_at = datetime.now()

        resp = MessageResponse.model_validate(MockMsg())
        assert resp.content == "test"
        assert resp.sources == [{"doc_id": 1}]


class TestFeedbackInput:
    def test_valid_feedback(self):
        obj = FeedbackInput(score=4)
        assert obj.score == 4
        assert obj.add_to_wrong is False

    def test_with_wrong_question(self):
        obj = FeedbackInput(
            score=2, add_to_wrong=True, correct_answer="A",
            user_answer="B", error_reason="misunderstanding", difficulty=3,
        )
        assert obj.add_to_wrong is True
        assert obj.error_reason == "misunderstanding"

    def test_score_min_boundary(self):
        obj = FeedbackInput(score=1)
        assert obj.score == 1

    def test_score_max_boundary(self):
        obj = FeedbackInput(score=5)
        assert obj.score == 5

    def test_score_below_min(self):
        with pytest.raises(ValidationError):
            FeedbackInput(score=0)

    def test_score_above_max(self):
        with pytest.raises(ValidationError):
            FeedbackInput(score=6)


# ==================== Auth Schemas ====================

class TestLoginInput:
    def test_valid(self):
        obj = LoginInput(username="admin", password="123456")
        assert obj.username == "admin"

    def test_empty_username(self):
        with pytest.raises(ValidationError):
            LoginInput(username="", password="123456")

    def test_empty_password(self):
        with pytest.raises(ValidationError):
            LoginInput(username="admin", password="")


class TestRegisterInput:
    def test_valid(self):
        obj = RegisterInput(username="newuser", email="new@test.com",
                            password="123456", role="user")
        assert obj.role == "user"

    def test_username_too_short(self):
        with pytest.raises(ValidationError):
            RegisterInput(username="ab", email="a@b.com", password="123456")

    def test_username_max_length(self):
        name = "a" * 50
        obj = RegisterInput(username=name, email="a@b.com", password="123456")
        assert len(obj.username) == 50

    def test_invalid_role(self):
        with pytest.raises(ValidationError):
            RegisterInput(username="test", email="a@b.com",
                          password="123456", role="moderator")

    def test_admin_role(self):
        obj = RegisterInput(username="admin2", email="admin2@test.com",
                            password="123456", role="admin")
        assert obj.role == "admin"

    def test_password_min_length(self):
        with pytest.raises(ValidationError):
            RegisterInput(username="test", email="a@b.com", password="12345")


class TestTokenOutput:
    def test_valid(self):
        obj = TokenOutput(access_token="abc", refresh_token="def")
        assert obj.token_type == "bearer"


# ==================== KB Schemas ====================

class TestDocumentCreate:
    def test_valid(self):
        obj = DocumentCreate(subject_id=1, title="文档", doc_type="textbook")
        assert obj.doc_type == "textbook"

    def test_invalid_doc_type(self):
        with pytest.raises(ValidationError):
            DocumentCreate(subject_id=1, title="文档", doc_type="invalid")


class TestDocumentFilter:
    def test_defaults(self):
        obj = DocumentFilter()
        assert obj.page == 1
        assert obj.size == 20

    def test_invalid_page(self):
        with pytest.raises(ValidationError):
            DocumentFilter(page=0)


# ==================== KG Schemas ====================

class TestKnowledgePointCreate:
    def test_valid(self):
        obj = KnowledgePointCreate(name="二叉树", subject_id=1)
        assert obj.difficulty == 3

    def test_empty_name(self):
        with pytest.raises(ValidationError):
            KnowledgePointCreate(name="", subject_id=1)

    def test_difficulty_range(self):
        with pytest.raises(ValidationError):
            KnowledgePointCreate(name="test", subject_id=1, difficulty=6)


class TestRelationCreate:
    def test_valid(self):
        obj = RelationCreate(source_id=1, target_id=2,
                             relation_type="PREREQUISITE")
        assert obj.relation_type == "PREREQUISITE"

    @pytest.mark.parametrize("rtype", ["PREREQUISITE", "NEXT", "RELATED",
                                       "CONTAINS", "CONTRAST", "EXAMINED_IN"])
    def test_valid_relation_types(self, rtype):
        obj = RelationCreate(source_id=1, target_id=2, relation_type=rtype)
        assert obj.relation_type == rtype

    def test_invalid_relation_type(self):
        with pytest.raises(ValidationError):
            RelationCreate(source_id=1, target_id=2, relation_type="INVALID")


class TestDocumentGenerateRequest:
    def test_valid(self):
        obj = DocumentGenerateRequest(subject_id=1, doc_type="study_guide")
        assert obj.doc_type == "study_guide"

    def test_invalid_doc_type(self):
        with pytest.raises(ValidationError):
            DocumentGenerateRequest(subject_id=1, doc_type="invalid")


# ==================== Notes Schemas ====================

class TestNoteCreate:
    def test_valid(self):
        obj = NoteCreate(subject_id=1, title="心得标题", content="心得体会内容")
        assert obj.title == "心得标题"

    def test_empty_content(self):
        with pytest.raises(ValidationError):
            NoteCreate(subject_id=1, title="标题", content="")

    def test_with_tags(self):
        obj = NoteCreate(subject_id=1, title="标题", content="内容",
                         tags=["数据结构", "算法"])
        assert len(obj.tags) == 2


class TestReviewInput:
    def test_approve(self):
        obj = ReviewInput(action="approve")
        assert obj.action == "approve"

    def test_reject_with_reason(self):
        obj = ReviewInput(action="reject", reject_reason="内容过少")
        assert obj.reject_reason == "内容过少"

    def test_invalid_action(self):
        with pytest.raises(ValidationError):
            ReviewInput(action="invalid")


class TestBatchReviewInput:
    def test_valid(self):
        obj = BatchReviewInput(ids=[1, 2, 3], action="approve")
        assert len(obj.ids) == 3

    def test_empty_ids(self):
        with pytest.raises(ValidationError):
            BatchReviewInput(ids=[], action="approve")

    def test_too_many_ids(self):
        with pytest.raises(ValidationError):
            BatchReviewInput(ids=list(range(101)), action="approve")


class TestCommentCreate:
    def test_valid(self):
        obj = CommentCreate(content="好文章！")
        assert obj.content == "好文章！"

    def test_empty_content(self):
        with pytest.raises(ValidationError):
            CommentCreate(content="")

    def test_content_max_length(self):
        with pytest.raises(ValidationError):
            CommentCreate(content="a" * 2001)


# ==================== Wrong Question Schemas ====================

class TestWrongQuestionCreate:
    def test_valid(self):
        obj = WrongQuestionCreate(subject_id=1, question_content="1+1=?")
        assert obj.difficulty == 3

    def test_with_error_reason(self):
        reasons = ["knowledge_gap", "misunderstanding", "careless", "other"]
        for reason in reasons:
            obj = WrongQuestionCreate(subject_id=1, question_content="q",
                                      error_reason=reason)
            assert obj.error_reason == reason

    def test_difficulty_range(self):
        with pytest.raises(ValidationError):
            WrongQuestionCreate(subject_id=1, question_content="q", difficulty=0)

    def test_difficulty_max(self):
        with pytest.raises(ValidationError):
            WrongQuestionCreate(subject_id=1, question_content="q", difficulty=6)


class TestStatsOutput:
    def test_valid(self):
        obj = StatsOutput(
            total=10, by_subject=[{"id": 1, "count": 5}],
            by_reason=[{"reason": "careless", "count": 3}],
            by_status=[{"status": "pending", "count": 7}],
        )
        assert obj.total == 10


# ==================== Notification Schemas ====================

class TestNotificationResponse:
    def test_valid(self):
        obj = NotificationResponse(
            id=1, type="system", title="通知标题",
            is_read=False, created_at=datetime.now(),
        )
        assert obj.is_read is False

    def test_from_attributes(self):
        class MockNotif:
            id = 1
            type = "note_approved"
            title = "通过"
            content = "你的心得已通过"
            related_id = 5
            is_read = True
            created_at = datetime.now()

        resp = NotificationResponse.model_validate(MockNotif())
        assert resp.is_read is True
        assert resp.related_id == 5


# ==================== System Schemas ====================

class TestKgExtractionSettings:
    def test_defaults(self):
        obj = KgExtractionSettings()
        assert obj.chunk_min_chars == 120
        assert obj.chunk_size == 512
        assert obj.chunk_overlap == 128

    def test_min_chars_validation(self):
        with pytest.raises(ValidationError):
            KgExtractionSettings(chunk_min_chars=10)

    def test_chunk_size_validation(self):
        with pytest.raises(ValidationError):
            KgExtractionSettings(chunk_size=6000)
