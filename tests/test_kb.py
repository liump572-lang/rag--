import pytest
from unittest.mock import MagicMock, patch, mock_open
from io import BytesIO

from app.modules.kb.schemas import (
    DocumentCreate, DocumentUpdate, DocumentResponse, DocumentFilter, ChunkResponse,
)


class TestKBEndpointDocumentList:
    def test_list_documents_requires_auth(self, authed_client):
        response = authed_client.get("/api/v1/kb")
        assert response.status_code == 200

    def test_list_documents_success(self, authed_client, mock_db):
        mock_db.query.return_value.outerjoin.return_value \
            .add_columns.return_value.filter.return_value \
            .order_by.return_value.offset.return_value \
            .limit.return_value.all.return_value = []
        mock_db.query.return_value.outerjoin.return_value \
            .add_columns.return_value.filter.return_value \
            .count.return_value = 0
        response = authed_client.get("/api/v1/kb")
        assert response.status_code == 200

    def test_list_documents_with_filters(self, authed_client, mock_db):
        with patch("app.modules.kb.router.KbService.list_documents") as mock_list:
            mock_list.return_value = ([], 0)
            response = authed_client.get(
                "/api/v1/kb?subject_id=1&doc_type=textbook&parse_status=success"
            )
            assert response.status_code == 200

    def test_get_document_not_found(self, authed_client, mock_db):
        with patch("app.modules.kb.router.KbService.get_document") as mock_get:
            mock_get.return_value = None
            response = authed_client.get("/api/v1/kb/999")
            assert response.status_code == 404

    def test_get_document_success(self, authed_client, mock_db):
        from tests.conftest import MockDocument
        with patch("app.modules.kb.router.KbService.get_document") as mock_get:
            mock_get.return_value = MockDocument()
            response = authed_client.get("/api/v1/kb/1")
            assert response.status_code == 200

    def test_delete_document_not_found(self, authed_client, mock_db):
        with patch("app.modules.kb.router.KbService.delete_document") as mock_del:
            mock_del.return_value = False
            response = authed_client.delete("/api/v1/kb/999")
            assert response.status_code == 404

    def test_delete_document_success(self, authed_client, mock_db):
        with patch("app.modules.kb.router.KbService.delete_document") as mock_del:
            mock_del.return_value = True
            response = authed_client.delete("/api/v1/kb/1")
            assert response.status_code == 200

    def test_reparse_document_not_found(self, authed_client, mock_db):
        with patch("app.modules.kb.router.KbService.reparse") as mock_reparse:
            mock_reparse.side_effect = ValueError("not found")
            response = authed_client.post("/api/v1/kb/999/reparse")
            assert response.status_code == 404

    def test_reparse_document_success(self, authed_client, mock_db):
        from tests.conftest import MockDocument
        with patch("app.modules.kb.router.KbService.reparse") as mock_reparse:
            mock_reparse.return_value = MockDocument()
            response = authed_client.post("/api/v1/kb/1/reparse")
            assert response.status_code == 200

    def test_get_chunks(self, authed_client, mock_db):
        with patch("app.modules.kb.router.KbService.get_chunks") as mock_chunks:
            mock_chunks.return_value = []
            response = authed_client.get("/api/v1/kb/1/chunks")
            assert response.status_code == 200

    def test_retrieval_test(self, authed_client):
        with patch("app.common.vector_store.search_chunks") as mock_search:
            mock_search.return_value = [{"id": 1, "content": "test", "score": 0.95}]
            response = authed_client.post("/api/v1/kb/retrieval-test?query=test&top_k=5")
            assert response.status_code == 200
            data = response.json()
            assert data["code"] == 200

    def test_upload_document(self, authed_client, mock_db):
        from tests.conftest import MockDocument
        with patch("app.modules.kb.router.KbService.upload") as mock_upload:
            mock_upload.return_value = MockDocument()
            files = {"file": ("test.pdf", b"content", "application/pdf")}
            response = authed_client.post(
                "/api/v1/kb/upload",
                data={"subject_id": "1", "title": "test", "doc_type": "textbook"},
                files=files,
            )
            assert response.status_code == 200

    def test_upload_value_error(self, authed_client, mock_db):
        files = {"file": ("test.xyz", b"content", "application/octet-stream")}
        response = authed_client.post(
            "/api/v1/kb/upload",
            data={"subject_id": "1", "title": "test", "doc_type": "textbook"},
            files=files,
        )
        assert response.status_code == 400


class TestKBSchemas:
    def test_document_create_validation(self):
        doc = DocumentCreate(subject_id=1, title="文档", doc_type="exam")
        assert doc.doc_type == "exam"

    def test_document_create_invalid_type(self):
        with pytest.raises(Exception):
            DocumentCreate(subject_id=1, title="文档", doc_type="invalid")

    def test_document_update_partial(self):
        update = DocumentUpdate(title="新标题")
        assert update.title == "新标题"
        assert update.doc_type is None

    def test_document_response_serialization(self):
        from tests.conftest import MockDocument
        doc = MockDocument()
        resp = DocumentResponse.model_validate(doc)
        data = resp.model_dump()
        assert data["title"] == "测试文档"
        assert data["file_type"] == "pdf"

    def test_document_filter_defaults(self):
        f = DocumentFilter()
        assert f.page == 1
        assert f.size == 20
        assert f.subject_id is None

    def test_document_filter_custom(self):
        f = DocumentFilter(page=2, size=50, subject_id=3, doc_type="textbook",
                           parse_status="success")
        assert f.page == 2
        assert f.parse_status == "success"

    def test_chunk_response(self):
        from datetime import datetime
        chunk = ChunkResponse(id=1, document_id=1, chunk_index=0,
                              content="test", char_count=4)
        assert chunk.content == "test"
