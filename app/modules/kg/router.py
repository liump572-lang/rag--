from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.common.response import error_response, paginated_response, success_response
from app.database import get_db
from app.middleware.auth import get_current_user
from app.models import User
from app.modules.kg.schemas import (
    DocumentGenerateRequest,
    KnowledgePointCreate,
    KnowledgePointResponse,
    KnowledgePointUpdate,
    RelationCreate,
    RelationResponse,
    RelationUpdate,
)
from app.modules.kg.service import KgService

router = APIRouter()


@router.get("/subgraph")
def get_subgraph(
    subject_id: Optional[int] = Query(None),
    depth: int = Query(2, ge=1, le=5),
    offset: int = Query(0, ge=0),
    size: int = Query(600, ge=100, le=2000),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    data = KgService.get_subgraph(db, subject_id, depth, offset, size)
    return success_response(data=data)


@router.get("/search")
def search_knowledge(
    keyword: str = Query(..., min_length=1),
    subject_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    results = KgService.search(db, keyword, subject_id)
    return success_response(data=results)


@router.get("/search-subgraph")
def search_subgraph(
    keyword: str = Query(..., min_length=1),
    subject_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    data = KgService.search_subgraph(db, keyword, subject_id)
    return success_response(data=data)


@router.get("/points")
def list_points(
    subject_id: Optional[int] = Query(None),
    keyword: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    items, total = KgService.list_points(db, subject_id, keyword, page, size)
    data = [KnowledgePointResponse.model_validate(p).model_dump() for p in items]
    return paginated_response(data, total, page, size)


@router.get("/points/{point_id}")
def get_point(
    point_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    point = KgService.get_point(db, point_id)
    if not point:
        return error_response(404, "知识点不存在")
    return success_response(data=KnowledgePointResponse.model_validate(point).model_dump())


@router.post("/points")
def create_point(
    body: KnowledgePointCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "admin":
        return error_response(403, "无权限")
    point = KgService.create_point(db, body.name, body.subject_id, body.description, body.difficulty)
    return success_response(data=KnowledgePointResponse.model_validate(point).model_dump())


@router.put("/points/{point_id}")
def update_point(
    point_id: int,
    body: KnowledgePointUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "admin":
        return error_response(403, "无权限")
    point = KgService.update_point(db, point_id, body.name, body.description, body.difficulty)
    if not point:
        return error_response(404, "知识点不存在")
    return success_response(data=KnowledgePointResponse.model_validate(point).model_dump())


@router.delete("/points/{point_id}")
def delete_point(
    point_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "admin":
        return error_response(403, "无权限")
    ok = KgService.delete_point(db, point_id)
    if not ok:
        return error_response(404, "知识点不存在")
    return success_response(message="知识点已删除")


@router.get("/relations")
def list_relations(
    subject_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rels = KgService.list_relations(db, subject_id)
    data = [RelationResponse.model_validate(r).model_dump() for r in rels]
    return success_response(data=data)


@router.post("/relations")
def create_relation(
    body: RelationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "admin":
        return error_response(403, "无权限")
    rel = KgService.create_relation(db, body.source_id, body.target_id, body.relation_type, body.description)
    if not rel:
        return error_response(400, "源节点和目标节点必须存在、不能相同且需要属于同一科目")
    return success_response(data=RelationResponse.model_validate(rel).model_dump())


@router.put("/relations/{relation_id}")
def update_relation(
    relation_id: int,
    body: RelationUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "admin":
        return error_response(403, "无权限")
    rel = KgService.update_relation(
        db,
        relation_id,
        body.source_id,
        body.target_id,
        body.relation_type,
        body.description,
    )
    if not rel:
        return error_response(400, "关系不存在，或源节点和目标节点不存在、相同、跨科目")
    return success_response(data=RelationResponse.model_validate(rel).model_dump())


@router.delete("/relations/{relation_id}")
def delete_relation(
    relation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "admin":
        return error_response(403, "无权限")
    ok = KgService.delete_relation(db, relation_id)
    if not ok:
        return error_response(404, "关系不存在")
    return success_response(message="关系已删除")


@router.post("/generate-document")
def generate_document(
    body: DocumentGenerateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "admin":
        return error_response(403, "无权限")
    try:
        doc = KgService.generate_document(db, body.subject_id, body.doc_type)
        return success_response(data={
            "id": doc.id,
            "title": doc.title,
            "doc_type": doc.doc_type,
            "file_type": doc.file_type,
            "parse_status": doc.parse_status,
            "created_at": doc.created_at.isoformat(),
        })
    except ValueError as e:
        return error_response(400, str(e))


@router.get("/rebuild/status")
def get_rebuild_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "admin":
        return error_response(403, "无权限")
    return success_response(data=KgService.rebuild_status(db))


@router.get("/documents/status")
def get_document_extraction_status(
    limit: int = Query(200, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "admin":
        return error_response(403, "无权限")
    return success_response(data=KgService.document_extraction_status(db, limit))


@router.post("/rebuild/retry-failed")
def retry_failed_rebuild_documents(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "admin":
        return error_response(403, "无权限")
    count = KgService.retry_failed_rebuild_documents(db)
    return success_response(data={"queued_documents": count})


@router.get("/relation-candidates")
def list_relation_candidates(
    status: str = Query("pending", pattern="^(pending|approved|rejected)$"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "admin":
        return error_response(403, "无权限")
    items, total = KgService.list_relation_candidates(db, status, page, size)
    return paginated_response(items, total, page, size)


@router.post("/relation-candidates/{candidate_id}/approve")
def approve_relation_candidate(
    candidate_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "admin":
        return error_response(403, "无权限")
    if not KgService.review_relation_candidate(db, candidate_id, True, current_user.id):
        return error_response(404, "候选关系不存在或已审核")
    return success_response(message="候选关系已批准")


@router.post("/relation-candidates/{candidate_id}/reject")
def reject_relation_candidate(
    candidate_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "admin":
        return error_response(403, "无权限")
    if not KgService.review_relation_candidate(db, candidate_id, False, current_user.id):
        return error_response(404, "候选关系不存在或已审核")
    return success_response(message="候选关系已驳回")
