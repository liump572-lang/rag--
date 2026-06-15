from typing import Optional

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from sqlalchemy.orm import Session

from app.common.response import error_response, paginated_response, success_response
from app.database import get_db
from app.modules.kb.schemas import DocumentResponse
from app.modules.kb.service import KbService

router = APIRouter()


@router.post("/upload")
def upload_document(
    subject_id: int = Form(...),
    title: str = Form(...),
    doc_type: str = Form(...),
    year: Optional[int] = Form(None),
    question_type: Optional[str] = Form(None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    try:
        doc = KbService.upload(db, subject_id, title, doc_type, file, year, question_type)
        return success_response(data=DocumentResponse.model_validate(doc))
    except ValueError as e:
        return error_response(400, str(e))


@router.get("")
def list_documents(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    subject_id: Optional[int] = Query(None),
    doc_type: Optional[str] = Query(None),
    file_type: Optional[str] = Query(None),
    parse_status: Optional[str] = Query(None),
    keyword: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    items, total = KbService.list_documents(
        db, page, size, subject_id, doc_type, file_type, parse_status, keyword,
    )
    data = [dict(row._mapping) for row in items]
    return paginated_response(data, total, page, size)


@router.post("/retrieval-test")
def retrieval_test(
    query: str = Query(..., min_length=1),
    top_k: int = Query(10, ge=1, le=50),
    subject_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
):
    from app.common.vector_store import search_chunks
    from app.models import Document
    where = None
    if subject_id:
        # Chroma 分片 metadata 只有 document_id，没有 subject_id；
        # 因此先把科目解析成它名下的文档 id 集合，再按 document_id 过滤。
        doc_ids = [row.id for row in db.query(Document.id).filter(Document.subject_id == subject_id).all()]
        if not doc_ids:
            return success_response(data=[])
        where = {"document_id": {"$in": doc_ids}}
    results = search_chunks(query, top_k=top_k, where=where)
    return success_response(data=results)


@router.get("/{document_id}")
def get_document(document_id: int, db: Session = Depends(get_db)):
    doc = KbService.get_document(db, document_id)
    if not doc:
        return error_response(404, "Document not found")
    return success_response(data=DocumentResponse.model_validate(doc))


@router.delete("/{document_id}")
def delete_document(document_id: int, db: Session = Depends(get_db)):
    ok = KbService.delete_document(db, document_id)
    if not ok:
        return error_response(404, "Document not found")
    return success_response(message="Document deleted")


@router.post("/{document_id}/reparse")
def reparse_document(document_id: int, db: Session = Depends(get_db)):
    try:
        doc = KbService.reparse(db, document_id)
        return success_response(data=DocumentResponse.model_validate(doc))
    except ValueError as e:
        return error_response(404, str(e))


@router.get("/{document_id}/chunks")
def get_chunks(document_id: int, db: Session = Depends(get_db)):
    chunks = KbService.get_chunks(db, document_id)
    return success_response(data=[
        {
            "id": c.id,
            "document_id": c.document_id,
            "chunk_index": c.chunk_index,
            "content": c.content,
            "char_count": c.char_count,
        }
        for c in chunks
    ])
