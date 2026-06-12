import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime

from app.modules.notification.schemas import NotificationResponse


class TestNotificationEndpoints:
    def test_list_notifications_requires_auth(self, client):
        response = client.get("/api/v1/notifications")
        assert response.status_code == 403

    def test_list_notifications_success(self, authed_client, mock_db):
        with patch(
            "app.modules.notification.router.NotificationService.list_for_user"
        ) as mock_list:
            mock_list.return_value = ([], 0)
            response = authed_client.get("/api/v1/notifications")
            assert response.status_code == 200

    def test_list_notifications_unread_only(self, authed_client, mock_db):
        with patch(
            "app.modules.notification.router.NotificationService.list_for_user"
        ) as mock_list:
            mock_list.return_value = ([], 0)
            response = authed_client.get("/api/v1/notifications?unread=true")
            assert response.status_code == 200

    def test_unread_count(self, authed_client, mock_db):
        with patch(
            "app.modules.notification.router.NotificationService.unread_count"
        ) as mock_count:
            mock_count.return_value = 5
            response = authed_client.get("/api/v1/notifications/unread-count")
            assert response.status_code == 200
            assert response.json()["data"]["count"] == 5

    def test_mark_read_not_found(self, authed_client, mock_db):
        with patch(
            "app.modules.notification.router.NotificationService.mark_read"
        ) as mock_read:
            mock_read.return_value = None
            response = authed_client.put("/api/v1/notifications/999/read")
            assert response.status_code == 404

    def test_mark_read_success(self, authed_client, mock_db):
        with patch(
            "app.modules.notification.router.NotificationService.mark_read"
        ) as mock_read:
            mock_read.return_value = MagicMock(
                id=1, type="system", title="通知",
                content="内容", related_id=None, is_read=True,
                created_at=datetime.now(),
            )
            response = authed_client.put("/api/v1/notifications/1/read")
            assert response.status_code == 200
            assert response.json()["data"]["is_read"] is True

    def test_mark_all_read(self, authed_client, mock_db):
        with patch(
            "app.modules.notification.router.NotificationService.mark_all_read"
        ) as mock_read:
            mock_read.return_value = 3
            response = authed_client.put("/api/v1/notifications/read-all")
            assert response.status_code == 200

    def test_pagination_defaults(self, authed_client, mock_db):
        with patch(
            "app.modules.notification.router.NotificationService.list_for_user"
        ) as mock_list:
            mock_list.return_value = ([], 0)
            response = authed_client.get("/api/v1/notifications")
            assert response.status_code == 200
            args = mock_list.call_args[0]
            assert args[2] == 1
            assert args[3] == 20


class TestNotificationSchemas:
    def test_notification_response_from_orm(self):
        notif = MagicMock(
            id=1, type="note_approved", title="通过",
            content="恭喜通过", related_id=5, is_read=False,
            created_at=datetime.now(),
        )
        resp = NotificationResponse.model_validate(notif)
        assert resp.type == "note_approved"
        assert resp.is_read is False
        assert resp.related_id == 5

    def test_notification_response_read_true(self):
        notif = MagicMock(
            id=1, type="system", title="通知",
            content=None, related_id=None, is_read=True,
            created_at=datetime.now(),
        )
        resp = NotificationResponse.model_validate(notif)
        assert resp.is_read is True
        assert resp.content is None

    def test_notification_response_serialization(self):
        notif = MagicMock(
            id=1, type="note_rejected", title="驳回",
            content="原因：内容不足", related_id=3, is_read=False,
            created_at=datetime.now(),
        )
        resp = NotificationResponse.model_validate(notif)
        data = resp.model_dump()
        assert data["title"] == "驳回"
        assert data["is_read"] is False
