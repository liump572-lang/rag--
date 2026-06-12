import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch

from app.modules.kg.schemas import (
    KnowledgePointCreate, KnowledgePointUpdate, KnowledgePointResponse,
    RelationCreate, RelationUpdate, RelationResponse,
    DocumentGenerateRequest, SubgraphResponse,
)


class FakeKnowledgePoint:
    def __init__(self, id=1, name="二叉树", subject_id=1, description="test",
                 difficulty=3, outline_path=None, neo4j_node_id=None,
                 origin="manual", confidence=1.0, review_status="approved"):
        self.id = id
        self.name = name
        self.subject_id = subject_id
        self.description = description
        self.difficulty = difficulty
        self.outline_path = outline_path
        self.neo4j_node_id = neo4j_node_id
        self.origin = origin
        self.confidence = confidence
        self.review_status = review_status
        self.created_at = datetime(2024, 1, 1)
        self.updated_at = datetime(2024, 1, 1)


class FakeRelation:
    def __init__(self, id=1, source_node_id=1, target_node_id=2,
                 relation_type="PREREQUISITE", description="desc",
                 origin="auto", confidence=0.9, review_status="pending"):
        self.id = id
        self.source_node_id = source_node_id
        self.target_node_id = target_node_id
        self.relation_type = relation_type
        self.description = description
        self.origin = origin
        self.confidence = confidence
        self.review_status = review_status


class TestKGEndpoints:
    def test_subgraph_requires_auth(self, client):
        response = client.get("/api/v1/kg/subgraph")
        assert response.status_code == 403

    def test_get_subgraph(self, authed_client, mock_db):
        with patch("app.modules.kg.router.KgService.get_subgraph") as mock_sg:
            mock_sg.return_value = {"nodes": [], "edges": []}
            response = authed_client.get("/api/v1/kg/subgraph")
            assert response.status_code == 200

    def test_get_subgraph_with_params(self, authed_client, mock_db):
        with patch("app.modules.kg.router.KgService.get_subgraph") as mock_sg:
            mock_sg.return_value = {"nodes": [], "edges": []}
            response = authed_client.get("/api/v1/kg/subgraph?subject_id=1&depth=3")
            assert response.status_code == 200

    def test_search_knowledge(self, authed_client, mock_db):
        with patch("app.modules.kg.router.KgService.search") as mock_search:
            mock_search.return_value = []
            response = authed_client.get("/api/v1/kg/search?keyword=二叉树")
            assert response.status_code == 200

    def test_search_empty_keyword(self, authed_client):
        response = authed_client.get("/api/v1/kg/search?keyword=")
        assert response.status_code == 422

    def test_search_subgraph(self, authed_client, mock_db):
        with patch("app.modules.kg.router.KgService.search_subgraph") as mock_ss:
            mock_ss.return_value = {"nodes": [], "edges": []}
            response = authed_client.get("/api/v1/kg/search-subgraph?keyword=排序")
            assert response.status_code == 200

    def test_list_points(self, authed_client, mock_db):
        with patch("app.modules.kg.router.KgService.list_points") as mock_list:
            mock_list.return_value = ([], 0)
            response = authed_client.get("/api/v1/kg/points")
            assert response.status_code == 200

    def test_get_point_not_found(self, authed_client, mock_db):
        with patch("app.modules.kg.router.KgService.get_point") as mock_get:
            mock_get.return_value = None
            response = authed_client.get("/api/v1/kg/points/999")
            assert response.json()["code"] == 404

    def test_get_point_success(self, authed_client, mock_db):
        with patch("app.modules.kg.router.KgService.get_point") as mock_get:
            mock_get.return_value = FakeKnowledgePoint()
            response = authed_client.get("/api/v1/kg/points/1")
            assert response.status_code == 200

    def test_create_point_non_admin(self, authed_client):
        response = authed_client.post("/api/v1/kg/points", json={
            "name": "新知识点", "subject_id": 1,
        })
        assert response.json()["code"] == 403

    def test_create_point_as_admin(self, admin_client, mock_db):
        with patch("app.modules.kg.router.KgService.create_point") as mock_create:
            mock_create.return_value = FakeKnowledgePoint(
                id=1, name="新知识点", subject_id=1, description=None,
                difficulty=3, review_status="pending",
            )
            response = admin_client.post("/api/v1/kg/points", json={
                "name": "新知识点", "subject_id": 1,
            })
            assert response.status_code == 200

    def test_update_point_non_admin(self, authed_client):
        response = authed_client.put("/api/v1/kg/points/1", json={"name": "改名"})
        assert response.json()["code"] == 403

    def test_update_point_as_admin(self, admin_client, mock_db):
        with patch("app.modules.kg.router.KgService.update_point") as mock_upd:
            mock_upd.return_value = FakeKnowledgePoint(
                id=1, name="改名", subject_id=1, description=None,
                difficulty=3, review_status="pending",
            )
            response = admin_client.put("/api/v1/kg/points/1",
                                        json={"name": "改名"})
            assert response.status_code == 200

    def test_delete_point_non_admin(self, authed_client):
        response = authed_client.delete("/api/v1/kg/points/1")
        assert response.json()["code"] == 403

    def test_delete_point_as_admin(self, admin_client, mock_db):
        with patch("app.modules.kg.router.KgService.delete_point") as mock_del:
            mock_del.return_value = True
            response = admin_client.delete("/api/v1/kg/points/1")
            assert response.status_code == 200

    def test_list_relations(self, authed_client, mock_db):
        with patch("app.modules.kg.router.KgService.list_relations") as mock_list:
            mock_list.return_value = []
            response = authed_client.get("/api/v1/kg/relations")
            assert response.status_code == 200

    def test_create_relation_non_admin(self, authed_client):
        response = authed_client.post("/api/v1/kg/relations", json={
            "source_id": 1, "target_id": 2,
            "relation_type": "PREREQUISITE",
        })
        assert response.json()["code"] == 403

    def test_delete_relation_as_admin(self, admin_client, mock_db):
        with patch("app.modules.kg.router.KgService.delete_relation") as mock_del:
            mock_del.return_value = True
            response = admin_client.delete("/api/v1/kg/relations/1")
            assert response.status_code == 200

    def test_generate_document_as_admin(self, admin_client, mock_db):
        with patch("app.modules.kg.router.KgService.generate_document") as mock_gen:
            from tests.conftest import MockDocument
            mock_gen.return_value = MockDocument()
            response = admin_client.post("/api/v1/kg/generate-document", json={
                "subject_id": 1, "doc_type": "study_guide",
            })
            assert response.status_code == 200

    def test_relation_candidates_list(self, admin_client, mock_db):
        with patch("app.modules.kg.router.KgService.list_relation_candidates") as mock_list:
            mock_list.return_value = ([], 0)
            response = admin_client.get("/api/v1/kg/relation-candidates")
            assert response.status_code == 200

    def test_approve_candidate(self, admin_client, mock_db):
        with patch("app.modules.kg.router.KgService.review_relation_candidate") as mock_rev:
            mock_rev.return_value = True
            response = admin_client.post("/api/v1/kg/relation-candidates/1/approve")
            assert response.status_code == 200

    def test_reject_candidate(self, admin_client, mock_db):
        with patch("app.modules.kg.router.KgService.review_relation_candidate") as mock_rev:
            mock_rev.return_value = True
            response = admin_client.post("/api/v1/kg/relation-candidates/1/reject")
            assert response.status_code == 200

    def test_rebuild_status(self, admin_client, mock_db):
        with patch("app.modules.kg.router.KgService.rebuild_status") as mock_rs:
            mock_rs.return_value = {"status": "idle"}
            response = admin_client.get("/api/v1/kg/rebuild/status")
            assert response.status_code == 200

    def test_retry_failed_rebuild(self, admin_client, mock_db):
        with patch("app.modules.kg.router.KgService.retry_failed_rebuild_documents") as mock_retry:
            mock_retry.return_value = 3
            response = admin_client.post("/api/v1/kg/rebuild/retry-failed")
            assert response.status_code == 200
            assert response.json()["data"]["queued_documents"] == 3


class TestKGSchemas:
    def test_knowledge_point_create_empty_name(self):
        with pytest.raises(Exception):
            KnowledgePointCreate(name="", subject_id=1)

    def test_knowledge_point_create_max_name_length(self):
        name = "a" * 100
        kp = KnowledgePointCreate(name=name, subject_id=1)
        assert len(kp.name) == 100

    def test_knowledge_point_update_all_fields(self):
        update = KnowledgePointUpdate(name="新名", description="desc", difficulty=4)
        assert update.name == "新名"
        assert update.difficulty == 4

    def test_knowledge_point_response_from_orm(self):
        kp = FakeKnowledgePoint(origin="auto", confidence=0.850, review_status="pending")
        resp = KnowledgePointResponse.model_validate(kp)
        assert resp.origin == "auto"
        assert resp.confidence == 0.850

    def test_relation_create_invalid_type(self):
        with pytest.raises(Exception):
            RelationCreate(source_id=1, target_id=2, relation_type="INVALID")

    @pytest.mark.parametrize("rtype", [
        "PREREQUISITE", "NEXT", "RELATED", "CONTAINS", "CONTRAST", "EXAMINED_IN",
    ])
    def test_relation_create_valid_types(self, rtype):
        rel = RelationCreate(source_id=1, target_id=2, relation_type=rtype)
        assert rel.relation_type == rtype

    def test_relation_response_from_orm(self):
        rel = FakeRelation()
        resp = RelationResponse.model_validate(rel)
        assert resp.relation_type == "PREREQUISITE"

    def test_document_generate_request(self):
        req = DocumentGenerateRequest(subject_id=1, doc_type="summary")
        assert req.doc_type == "summary"

    def test_document_generate_invalid_type(self):
        with pytest.raises(Exception):
            DocumentGenerateRequest(subject_id=1, doc_type="invalid")
