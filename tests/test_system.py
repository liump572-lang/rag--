import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime

from app.modules.system.schemas import (
    SettingsUpdate, KgExtractionSettings, SystemConfigCreate,
    SystemConfigUpdate, SystemConfigResponse,
)


class TestSystemEndpoints:
    def test_list_models(self, client):
        response = client.get("/api/v1/admin/system/models")
        assert response.status_code == 200
        data = response.json()
        assert len(data["data"]) >= 4
        models = [m["value"] for m in data["data"]]
        assert "deepseek-v4-flash" in models

    def test_get_settings_non_admin(self, authed_client):
        response = authed_client.get("/api/v1/admin/system/settings")
        assert response.status_code == 403

    def test_get_settings_as_admin(self, admin_client, mock_db):
        mock_db.query.return_value.filter.return_value.first.return_value = None
        response = admin_client.get("/api/v1/admin/system/settings")
        assert response.status_code == 200

    def test_update_settings_non_admin(self, authed_client):
        response = authed_client.put("/api/v1/admin/system/settings",
                                     json={"llm_model": "deepseek-v4-pro"})
        assert response.status_code == 403

    def test_update_settings_as_admin(self, admin_client, mock_db):
        mock_db.query.return_value.filter.return_value.first.return_value = None
        response = admin_client.put("/api/v1/admin/system/settings", json={
            "llm_model": "deepseek-v4-pro",
        })
        assert response.status_code == 200

    def test_get_kg_settings_non_admin(self, authed_client):
        response = authed_client.get("/api/v1/admin/system/kg-extraction-settings")
        assert response.status_code == 403

    def test_get_kg_settings_as_admin(self, admin_client, mock_db):
        with patch("app.common.kg_settings.get_kg_settings") as mock_kg:
            mock_kg.return_value = {
                "chunk.min_chars": 120,
                "chunk.size": 512,
                "chunk.overlap": 50,
                "kg.relation_candidate_threshold": 0.6,
                "kg.relation_auto_threshold": 0.85,
            }
            response = admin_client.get(
                "/api/v1/admin/system/kg-extraction-settings"
            )
            assert response.status_code == 200

    def test_update_kg_settings_as_admin(self, admin_client, mock_db):
        mock_db.query.return_value.filter.return_value.first.return_value = None
        with patch("app.common.kg_settings.validate_kg_settings") as mock_validate:
            mock_validate.return_value = {
                "chunk.min_chars": 200,
                "chunk.size": 1024,
                "chunk.overlap": 100,
                "kg.relation_candidate_threshold": 0.7,
                "kg.relation_auto_threshold": 0.9,
            }
            response = admin_client.put(
                "/api/v1/admin/system/kg-extraction-settings", json={
                    "chunk_min_chars": 200,
                    "chunk_size": 1024,
                    "chunk_overlap": 100,
                    "relation_candidate_threshold": 0.7,
                    "relation_auto_threshold": 0.9,
                })
            assert response.status_code == 200

    def test_list_configs_non_admin(self, authed_client):
        response = authed_client.get("/api/v1/admin/system/configs")
        assert response.status_code == 403

    def test_list_configs_as_admin(self, admin_client, mock_db):
        with patch(
            "app.modules.system.router.SystemConfigService.list"
        ) as mock_list:
            mock_list.return_value = []
            response = admin_client.get("/api/v1/admin/system/configs")
            assert response.status_code == 200

    def test_get_config_as_admin(self, admin_client, mock_db):
        with patch(
            "app.modules.system.router.SystemConfigService.get"
        ) as mock_get:
            mock_get.return_value = MagicMock(
                id=1, config_key="test", config_value="val",
                description="desc", updated_by=1,
                created_at=datetime.now(), updated_at=datetime.now(),
            )
            response = admin_client.get("/api/v1/admin/system/configs/1")
            assert response.status_code == 200

    def test_get_config_not_found(self, admin_client, mock_db):
        with patch(
            "app.modules.system.router.SystemConfigService.get"
        ) as mock_get:
            mock_get.return_value = None
            response = admin_client.get("/api/v1/admin/system/configs/999")
            assert response.status_code == 404

    def test_create_config_as_admin(self, admin_client, mock_db):
        with patch(
            "app.modules.system.router.SystemConfigService.get_by_key"
        ) as mock_check:
            mock_check.return_value = None
            with patch(
                "app.modules.system.router.SystemConfigService.create"
            ) as mock_create:
                mock_create.return_value = MagicMock(
                    id=1, config_key="new_key", config_value="val",
                    description="desc", updated_by=1,
                    created_at=datetime.now(), updated_at=datetime.now(),
                )
                response = admin_client.post(
                    "/api/v1/admin/system/configs",
                    json={"config_key": "new_key", "config_value": "val"},
                )
                assert response.status_code == 200

    def test_create_duplicate_config(self, admin_client, mock_db):
        with patch(
            "app.modules.system.router.SystemConfigService.get_by_key"
        ) as mock_check:
            mock_check.return_value = MagicMock()
            response = admin_client.post(
                "/api/v1/admin/system/configs",
                json={"config_key": "existing", "config_value": "val"},
            )
            assert response.status_code == 400

    def test_update_config_as_admin(self, admin_client, mock_db):
        with patch(
            "app.modules.system.router.SystemConfigService.update"
        ) as mock_upd:
            mock_upd.return_value = MagicMock(
                id=1, config_key="test", config_value="new_val",
                description="desc", updated_by=1,
                created_at=datetime.now(), updated_at=datetime.now(),
            )
            response = admin_client.put(
                "/api/v1/admin/system/configs/1",
                json={"config_value": "new_val"},
            )
            assert response.status_code == 200

    def test_delete_config_as_admin(self, admin_client, mock_db):
        with patch(
            "app.modules.system.router.SystemConfigService.delete"
        ) as mock_del:
            mock_del.return_value = True
            response = admin_client.delete("/api/v1/admin/system/configs/1")
            assert response.status_code == 200

    def test_delete_config_not_found(self, admin_client, mock_db):
        with patch(
            "app.modules.system.router.SystemConfigService.delete"
        ) as mock_del:
            mock_del.return_value = False
            response = admin_client.delete("/api/v1/admin/system/configs/999")
            assert response.status_code == 404


class TestSystemSchemas:
    def test_settings_update_partial(self):
        update = SettingsUpdate(llm_model="deepseek-v4-pro")
        assert update.llm_model == "deepseek-v4-pro"
        assert update.api_base is None

    def test_kg_extraction_settings_validation(self):
        settings = KgExtractionSettings(
            chunk_min_chars=100, chunk_size=500, chunk_overlap=50,
            relation_candidate_threshold=0.5, relation_auto_threshold=0.8,
        )
        assert settings.chunk_min_chars == 100

    def test_kg_extraction_settings_minimums(self):
        settings = KgExtractionSettings(
            chunk_min_chars=20, chunk_size=100, chunk_overlap=10,
            relation_candidate_threshold=0.0, relation_auto_threshold=0.0,
        )
        assert settings.chunk_min_chars == 20

    def test_kg_extraction_settings_maximums(self):
        settings = KgExtractionSettings(
            chunk_min_chars=2000, chunk_size=5000, chunk_overlap=2000,
            relation_candidate_threshold=1.0, relation_auto_threshold=1.0,
        )
        assert settings.chunk_size == 5000

    @pytest.mark.parametrize("field,value", [
        ("chunk_min_chars", 10),
        ("chunk_size", 50),
        ("chunk_overlap", -1),
        ("relation_candidate_threshold", -0.1),
        ("relation_auto_threshold", 1.5),
    ])
    def test_invalid_values(self, field, value):
        kwargs = {
            "chunk_min_chars": 120, "chunk_size": 512,
            "chunk_overlap": 50, "relation_candidate_threshold": 0.6,
            "relation_auto_threshold": 0.85,
        }
        kwargs[field] = value
        with pytest.raises(Exception):
            KgExtractionSettings(**kwargs)
