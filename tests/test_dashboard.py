import pytest
from unittest.mock import MagicMock, patch

from app.main import app
from app.database import get_db


class TestDashboardEndpoints:
    def test_dashboard_requires_auth(self, client):
        response = client.get("/api/v1/admin/dashboard")
        assert response.status_code == 403

    def test_dashboard_non_admin_forbidden(self, authed_client):
        response = authed_client.get("/api/v1/admin/dashboard")
        assert response.status_code == 403

    def test_dashboard_as_admin(self, admin_client, mock_db):
        query_mock = MagicMock()
        query_mock.scalar.side_effect = [100, 50, 200, 300, 80, 40]
        mock_db.query.return_value = query_mock

        mock_db.query.return_value.outerjoin.return_value \
            .group_by.return_value.order_by.return_value \
            .all.return_value = [(1, "数据结构", 10), (2, "算法", 5)]

        mock_db.query.return_value.group_by.return_value \
            .all.return_value = [("textbook", 20), ("exam", 15)]

        mock_db.query.return_value.filter.return_value \
            .group_by.return_value.order_by.return_value \
            .all.return_value = [("2024-01-01", 5)]

        response = admin_client.get("/api/v1/admin/dashboard")
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200
        assert "total_users" in data["data"]
        assert data["data"]["total_users"] == 100

    def test_dashboard_data_structure(self, admin_client, mock_db):
        query_mock = MagicMock()
        query_mock.scalar.side_effect = [10, 5, 15, 20, 3, 7]
        mock_db.query.return_value = query_mock
        mock_db.query.return_value.outerjoin.return_value \
            .group_by.return_value.order_by.return_value \
            .all.return_value = []
        mock_db.query.return_value.group_by.return_value \
            .all.return_value = []
        mock_db.query.return_value.filter.return_value \
            .group_by.return_value.order_by.return_value \
            .all.return_value = []

        response = admin_client.get("/api/v1/admin/dashboard")
        data = response.json()["data"]
        expected_keys = [
            "total_users", "total_documents", "total_conversations",
            "total_knowledge_points", "total_notes", "total_wrong_questions",
            "docs_by_subject", "docs_by_type", "recent_conversations",
        ]
        for key in expected_keys:
            assert key in data, f"Missing key: {key}"


class TestHealthEndpoint:
    def test_health_check(self, client):
        response = client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200
        assert data["data"]["status"] == "ok"
        assert data["data"]["version"] == "1.0.0"


class TestRootEndpoint:
    def test_root(self, client):
        response = client.get("/")
        assert response.status_code == 200
        assert "API" in response.json()["message"]


class TestSubjectsEndpoint:
    def test_list_subjects(self, client, mock_db):
        mock_db.query.return_value.order_by.return_value.all.return_value = []
        app.dependency_overrides.clear()
        app.dependency_overrides[get_db] = lambda: mock_db
        response = client.get("/api/v1/subjects")
        assert response.status_code == 200
        app.dependency_overrides.clear()

    def test_list_subjects_with_data(self, client, mock_db):
        class FakeSubject:
            def __init__(self, id, name, description, is_built_in, sort_order):
                self.id = id
                self.name = name
                self.description = description
                self.is_built_in = is_built_in
                self.sort_order = sort_order

        mock_subject_1 = FakeSubject(1, "数据结构", "desc", 0, 1)
        mock_subject_2 = FakeSubject(2, "算法", "desc", 1, 2)
        mock_db.query.return_value.order_by.return_value \
            .all.return_value = [mock_subject_1, mock_subject_2]

        app.dependency_overrides.clear()
        app.dependency_overrides[get_db] = lambda: mock_db

        response = client.get("/api/v1/subjects")
        data = response.json()
        assert len(data["data"]) == 2
        assert data["data"][0]["name"] == "数据结构"
        assert data["data"][1]["is_built_in"] is True
        app.dependency_overrides.clear()
