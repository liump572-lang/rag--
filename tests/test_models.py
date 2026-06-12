import pytest
from datetime import datetime

from app.models import (
    User, Subject, Document, DocumentChunk, Conversation, Message,
    WrongQuestion, StudyNote, NoteComment, NoteFavorite, NoteLike,
    SystemConfig, SystemLog, KnowledgePoint, KnowledgeRelation,
    KnowledgeRelationEvidence, KnowledgeRelationCandidate,
    KnowledgePointSource, KgExtractionRun, KgExtractionBatch,
    KgRebuild, KgSyncFailure, Notification, ExamPaper, ExamQuestion,
    ThirdPartyApi,
)


class TestUserModel:
    def test_create_user(self):
        user = User(
            username="testuser", email="test@example.com",
            password_hash="hashed", role="user", status="active",
            total_questions=0, wrong_question_count=0,
        )
        assert user.username == "testuser"
        assert user.role == "user"
        assert user.status == "active"
        assert user.total_questions == 0
        assert user.wrong_question_count == 0

    def test_admin_user(self):
        user = User(
            username="admin", email="admin@test.com",
            password_hash="hash", role="admin", status="active",
        )
        assert user.role == "admin"

    def test_tablename(self):
        assert User.__tablename__ == "users"

    def test_relationships_defined(self):
        user = User(username="u", email="u@t.com", password_hash="h")
        assert hasattr(user, "conversations")
        assert hasattr(user, "wrong_questions")
        assert hasattr(user, "study_notes")

    def test_column_types_exist(self):
        assert hasattr(User, "id")
        assert hasattr(User, "username")
        assert hasattr(User, "password_hash")

    def test_password_hash_max_length(self):
        col = User.__table__.c.password_hash
        assert col.type.length == 255


class TestSubjectModel:
    def test_create_subject(self):
        subject = Subject(
            name="数据结构", description="数据结构与算法",
            sort_order=1, is_built_in=0,
        )
        assert subject.name == "数据结构"
        assert subject.sort_order == 1

    def test_built_in(self):
        subject = Subject(name="操作系统", is_built_in=1)
        assert subject.is_built_in == 1

    def test_tablename(self):
        assert Subject.__tablename__ == "subjects"


class TestDocumentModel:
    def test_create_document(self):
        doc = Document(
            subject_id=1, title="测试文档", file_path="/tmp/test.pdf",
            file_type="pdf", doc_type="textbook",
            parse_status="pending", chunk_count=0, parse_revision=0,
        )
        assert doc.parse_status == "pending"
        assert doc.chunk_count == 0
        assert doc.parse_revision == 0

    def test_tablename(self):
        assert Document.__tablename__ == "documents"


class TestConversationModel:
    def test_create_conversation(self):
        conv = Conversation(
            user_id=1, subject_id=1, title="测试对话", message_count=0,
        )
        assert conv.message_count == 0

    def test_tablename(self):
        assert Conversation.__tablename__ == "conversations"


class TestMessageModel:
    def test_create_message(self):
        msg = Message(
            conversation_id=1, role="user", content="你好", token_count=0,
        )
        assert msg.role == "user"
        assert msg.token_count == 0

    def test_all_roles(self):
        for role in ["user", "assistant", "system"]:
            msg = Message(conversation_id=1, role=role, content="test")
            assert msg.role == role

    def test_tablename(self):
        assert Message.__tablename__ == "messages"


class TestWrongQuestionModel:
    def test_create_wrong_q(self):
        wq = WrongQuestion(
            user_id=1, subject_id=1, question_content="1+1=?",
            correct_answer="2", user_answer="3",
            mastery_status="pending", review_count=0,
        )
        assert wq.mastery_status == "pending"
        assert wq.review_count == 0

    def test_with_error_reason(self):
        wq = WrongQuestion(
            user_id=1, subject_id=1, question_content="q",
            error_reason="careless", mastery_status="pending",
        )
        assert wq.error_reason == "careless"

    def test_tablename(self):
        assert WrongQuestion.__tablename__ == "wrong_questions"


class TestStudyNoteModel:
    def test_create_note(self):
        note = StudyNote(
            user_id=1, subject_id=1, title="心得", content="内容",
            status="pending", like_count=0, comment_count=0,
        )
        assert note.status == "pending"
        assert note.like_count == 0
        assert note.comment_count == 0

    def test_published_note(self):
        note = StudyNote(
            user_id=1, subject_id=1, title="t", content="c",
            status="published", is_pinned=1,
        )
        assert note.status == "published"
        assert note.is_pinned == 1

    def test_tablename(self):
        assert StudyNote.__tablename__ == "study_notes"


class TestNoteCommentModel:
    def test_create_comment(self):
        comment = NoteComment(note_id=1, user_id=1, content="好文章")
        assert comment.content == "好文章"

    def test_tablename(self):
        assert NoteComment.__tablename__ == "note_comments"


class TestKnowledgePointModel:
    def test_create_point(self):
        kp = KnowledgePoint(
            name="二叉树", subject_id=1,
            origin="legacy", confidence=1.000, review_status="pending",
        )
        assert kp.origin == "legacy"
        assert kp.review_status == "pending"

    def test_auto_extracted(self):
        kp = KnowledgePoint(
            name="测试", subject_id=1, origin="auto",
            confidence=0.850, review_status="pending",
        )
        assert kp.origin == "auto"
        assert kp.confidence == 0.850

    def test_tablename(self):
        assert KnowledgePoint.__tablename__ == "knowledge_points"

    def test_column_definitions(self):
        cols = KnowledgePoint.__table__.c
        assert cols.origin.default is not None


class TestKnowledgeRelationModel:
    def test_create_relation(self):
        rel = KnowledgeRelation(
            source_node_id=1, target_node_id=2,
            relation_type="PREREQUISITE", origin="legacy",
        )
        assert rel.origin == "legacy"

    def test_tablename(self):
        assert KnowledgeRelation.__tablename__ == "knowledge_relations"

    def test_relation_type_enum(self):
        rel = KnowledgeRelation(
            source_node_id=1, target_node_id=2,
            relation_type="RELATED",
        )
        assert rel.relation_type == "RELATED"


class TestSystemConfigModel:
    def test_create_config(self):
        cfg = SystemConfig(config_key="test_key", config_value="test_value")
        assert cfg.config_key == "test_key"

    def test_tablename(self):
        assert SystemConfig.__tablename__ == "system_configs"


class TestSystemLogModel:
    def test_create_log(self):
        log = SystemLog(
            action="login", module="auth", message="用户登录", level="INFO",
        )
        assert log.level == "INFO"

    def test_tablename(self):
        assert SystemLog.__tablename__ == "system_logs"


class TestNotificationModel:
    def test_create_notification(self):
        notif = Notification(
            user_id=1, type="system", title="通知",
            content="系统通知内容", is_read=0,
        )
        assert notif.is_read == 0

    def test_tablename(self):
        assert Notification.__tablename__ == "notifications"


class TestExamPaperModel:
    def test_create_paper(self):
        paper = ExamPaper(
            subject_id=1, year=2024, title="2024年真题",
            question_count=0, source="uploaded",
        )
        assert paper.question_count == 0
        assert paper.source == "uploaded"

    def test_tablename(self):
        assert ExamPaper.__tablename__ == "exam_papers"


class TestExamQuestionModel:
    def test_create_question(self):
        q = ExamQuestion(
            exam_paper_id=1, question_type="choice",
            content="1+1=?", difficulty=3,
        )
        assert q.difficulty == 3

    def test_tablename(self):
        assert ExamQuestion.__tablename__ == "exam_questions"

    def test_question_type_choices(self):
        for qt in ["choice", "fill", "short_answer", "calculation", "comprehensive"]:
            q = ExamQuestion(exam_paper_id=1, question_type=qt, content="test")
            assert q.question_type == qt


class TestThirdPartyApiModel:
    def test_create_api(self):
        api = ThirdPartyApi(
            name="test", api_url="https://api.test.com",
            is_enabled=1, sync_interval=3600,
        )
        assert api.is_enabled == 1
        assert api.sync_interval == 3600

    def test_tablename(self):
        assert ThirdPartyApi.__tablename__ == "third_party_apis"


class TestKgExtractionRunModel:
    def test_create_run(self):
        run = KgExtractionRun(
            document_id=1, version="1.0", status="queued",
            batch_count=0, processed_batches=0,
        )
        assert run.status == "queued"
        assert run.batch_count == 0

    def test_tablename(self):
        assert KgExtractionRun.__tablename__ == "kg_extraction_runs"


class TestKgRebuildModel:
    def test_create_rebuild(self):
        rebuild = KgRebuild(
            version="v2024-01-01", status="queued",
            total_documents=0, completed_documents=0, failed_documents=0,
        )
        assert rebuild.status == "queued"

    def test_tablename(self):
        assert KgRebuild.__tablename__ == "kg_rebuilds"


class TestKgSyncFailureModel:
    def test_create_failure(self):
        failure = KgSyncFailure(
            operation="create_node", entity_type="point",
            payload={}, error_msg="连接超时", status="pending",
        )
        assert failure.status == "pending"

    def test_tablename(self):
        assert KgSyncFailure.__tablename__ == "kg_sync_failures"


class TestModelTablenames:
    def test_all_tablenames(self):
        models_with_tables = [
            (User, "users"), (Subject, "subjects"),
            (Document, "documents"), (DocumentChunk, "document_chunks"),
            (Conversation, "conversations"), (Message, "messages"),
            (WrongQuestion, "wrong_questions"),
            (StudyNote, "study_notes"), (NoteComment, "note_comments"),
            (NoteFavorite, "note_favorites"), (NoteLike, "note_likes"),
            (SystemConfig, "system_configs"), (SystemLog, "system_logs"),
            (KnowledgePoint, "knowledge_points"),
            (KnowledgeRelation, "knowledge_relations"),
            (Notification, "notifications"),
            (ExamPaper, "exam_papers"), (ExamQuestion, "exam_questions"),
            (ThirdPartyApi, "third_party_apis"),
            (KgExtractionRun, "kg_extraction_runs"),
            (KgExtractionBatch, "kg_extraction_batches"),
            (KgRebuild, "kg_rebuilds"),
            (KgSyncFailure, "kg_sync_failures"),
        ]
        for model_cls, expected_table in models_with_tables:
            assert model_cls.__tablename__ == expected_table, \
                f"{model_cls.__name__} tablename mismatch"

    def test_relationships_present(self):
        model_rels = {
            User: ["conversations", "wrong_questions", "study_notes"],
            Document: ["chunks"],
            Conversation: ["user", "messages"],
            Message: ["conversation"],
            WrongQuestion: ["user"],
            StudyNote: ["user"],
        }
        for model_cls, rel_names in model_rels.items():
            for rel_name in rel_names:
                assert hasattr(model_cls, rel_name), \
                    f"{model_cls.__name__} missing relationship '{rel_name}'"
