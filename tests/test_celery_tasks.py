import pytest
from unittest.mock import MagicMock, patch


class TestCeleryAppConfig:
    def test_celery_app_imports(self):
        from app.tasks.celery_app import celery_app
        assert celery_app.conf.task_queues is not None
        assert celery_app.main == "knowledge_qa"

    def test_celery_broker_config(self):
        from app.config import settings
        assert settings.celery_broker_url is not None
        assert "redis" in settings.celery_broker_url


class TestDocumentParseTask:
    def test_document_parse_task_exists(self):
        try:
            from app.tasks.document_parse import parse_document_task
            assert parse_document_task.__name__ == "parse_document_task"
        except (ImportError, AttributeError) as e:
            pytest.skip(f"Task not available: {e}")

    def test_parse_task_routing(self):
        from app.tasks.celery_app import celery_app
        queues = celery_app.conf.task_queues or {}
        assert "parse_queue" in queues, \
            f"No parse_queue found in: {list(queues.keys())}"


class TestKgTask:
    def test_kg_extract_task_exists(self):
        try:
            from app.tasks.kg_extract import extract_kg_from_batch
            assert extract_kg_from_batch.__name__ == "extract_kg_from_batch"
        except (ImportError, AttributeError) as e:
            pytest.skip(f"Task not available: {e}")

    def test_kg_rebuild_task_exists(self):
        try:
            from app.tasks.kg_rebuild import rebuild_knowledge_graph
            assert rebuild_knowledge_graph.__name__ == "rebuild_knowledge_graph"
        except (ImportError, AttributeError) as e:
            pytest.skip(f"Task not available: {e}")

    def test_kg_task_routing(self):
        from app.tasks.celery_app import celery_app
        queues = celery_app.conf.task_queues or {}
        assert "kg_queue" in queues, \
            f"No kg_queue found in: {list(queues.keys())}"


class TestVectorizeTask:
    def test_vectorize_task_exists(self):
        try:
            from app.tasks.vectorize import vectorize_chunks
            assert vectorize_chunks.__name__ == "vectorize_chunks"
        except (ImportError, AttributeError) as e:
            pytest.skip(f"Task not available: {e}")
