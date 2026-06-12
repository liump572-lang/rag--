import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from datetime import datetime, timedelta
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app.database import get_db
from app.middleware.auth import get_current_user, security
from app.models import User, Subject, Document, DocumentChunk, Conversation, Message
from app.modules.auth.schemas import UserInfo

# ==================== Mock Data Factory ====================

class MockUser:
    def __init__(self, id=1, username="testuser", email="test@example.com",
                 role="user", status="active", password_hash="hashed_pwd"):
        self.id = id
        self.username = username
        self.email = email
        self.password_hash = password_hash
        self.role = role
        self.status = status
        self.total_questions = 0
        self.wrong_question_count = 0
        self.last_login_at = None
        self.created_at = datetime.now()
        self.updated_at = datetime.now()

class MockSubject:
    def __init__(self, id=1, name="数据结构", description="数据结构与算法",
                 sort_order=1, is_built_in=0):
        self.id = id
        self.name = name
        self.description = description
        self.sort_order = sort_order
        self.is_built_in = is_built_in
        self.created_at = datetime.now()

class MockDocument:
    def __init__(self, id=1, subject_id=1, title="测试文档", file_path="/tmp/test.pdf",
                 file_size=1024, file_type="pdf", doc_type="textbook",
                 parse_status="success", chunk_count=5, parse_revision=1):
        self.id = id
        self.subject_id = subject_id
        self.title = title
        self.file_path = file_path
        self.file_size = file_size
        self.file_type = file_type
        self.doc_type = doc_type
        self.parse_status = parse_status
        self.error_msg = None
        self.chunk_count = chunk_count
        self.parse_revision = parse_revision
        self.year = None
        self.question_type = None
        self.created_at = datetime.now()
        self.updated_at = datetime.now()

class MockConversation:
    def __init__(self, id=1, user_id=1, subject_id=1, title="测试对话", message_count=3):
        self.id = id
        self.user_id = user_id
        self.subject_id = subject_id
        self.title = title
        self.message_count = message_count
        self.created_at = datetime.now()
        self.updated_at = datetime.now()

class MockMessage:
    def __init__(self, id=1, conversation_id=1, role="user", content="你好",
                 sources=None, question_type="knowledge", feedback_score=None,
                 token_count=10):
        self.id = id
        self.conversation_id = conversation_id
        self.role = role
        self.content = content
        self.sources = sources or []
        self.question_type = question_type
        self.intent_confidence = 0.95
        self.feedback_score = feedback_score
        self.token_count = token_count
        self.created_at = datetime.now()

# ==================== Fixtures ====================

@pytest.fixture
def mock_db():
    db = MagicMock(spec=Session)
    db.add = MagicMock()
    db.commit = MagicMock()
    db.refresh = MagicMock()
    db.flush = MagicMock()
    db.query = MagicMock()
    db.close = MagicMock()
    return db

@pytest.fixture
def mock_admin_user():
    return MockUser(id=1, username="admin", email="admin@example.com", role="admin")

@pytest.fixture
def mock_normal_user():
    return MockUser(id=2, username="student", email="student@example.com", role="user")

@pytest.fixture
def mock_subject():
    return MockSubject()

@pytest.fixture
def mock_document():
    return MockDocument()

@pytest.fixture
def mock_conversation():
    return MockConversation()

@pytest.fixture
def mock_message():
    return MockMessage()

@pytest.fixture
def override_get_db(mock_db):
    async def _override():
        yield mock_db
    app.dependency_overrides[get_db] = _override
    yield
    app.dependency_overrides.pop(get_db, None)

@pytest.fixture
def override_get_current_user(mock_normal_user):
    async def _override():
        return mock_normal_user
    app.dependency_overrides[get_current_user] = _override
    yield
    app.dependency_overrides.pop(get_current_user, None)

@pytest.fixture
def override_get_admin_user(mock_admin_user):
    async def _override():
        return mock_admin_user
    app.dependency_overrides[get_current_user] = _override
    yield
    app.dependency_overrides.pop(get_current_user, None)

@pytest.fixture
def client():
    return TestClient(app)

@pytest.fixture
def authed_client(client, override_get_db, override_get_current_user):
    return client

@pytest.fixture
def admin_client(client, override_get_db, override_get_admin_user):
    return client

@pytest.fixture
def mock_query_chain(mock_db):
    def chain(*filters):
        q = MagicMock()
        q.filter.return_value = q
        q.filter_by.return_value = q
        q.order_by.return_value = q
        q.limit.return_value = q
        q.offset.return_value = q
        q.all.return_value = []
        q.first.return_value = None
        q.count.return_value = 0
        q.scalar.return_value = 0
        q.group_by.return_value = q
        q.outerjoin.return_value = q
        mock_db.query.return_value = q
        return q
    return chain

@pytest.fixture(autouse=True)
def reset_dependency_overrides():
    yield
    app.dependency_overrides.clear()
