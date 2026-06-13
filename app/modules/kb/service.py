import os
from datetime import datetime
from typing import Optional

from sqlalchemy import and_, exists, or_
from sqlalchemy.orm import Session

from app.common.parsers import parse_document
from app.common.utils import generate_filename
from app.config import settings
from app.models import (
    Document,
    DocumentChunk,
    KgExtractionBatch,
    KgExtractionRun,
    KgSyncFailure,
    KnowledgePoint,
    KnowledgePointSource,
    KnowledgeRelation,
    KnowledgeRelationCandidate,
    KnowledgeRelationEvidence,
    Subject,
)


ALLOWED_EXTENSIONS = {"pdf", "docx", "pptx", "txt", "md"}
FILE_TYPE_MAP = {
    ".pdf": "pdf", ".docx": "docx", ".pptx": "pptx",
    ".txt": "txt", ".md": "md",
}


class KbService:

    @staticmethod
    def upload(
        db: Session,
        subject_id: int,
        title: str,
        doc_type: str,
        file,
        year: Optional[int] = None,
        question_type: Optional[str] = None,
    ) -> Document:
        ext = os.path.splitext(file.filename)[1].lower()
        if ext not in FILE_TYPE_MAP:
            raise ValueError(f"Unsupported file type: {ext}")
        file_type = FILE_TYPE_MAP[ext]

        subject_dir = os.path.join(settings.upload_dir, str(subject_id))
        os.makedirs(subject_dir, exist_ok=True)

        stored_name = generate_filename(file_type)
        file_path = os.path.join(subject_dir, stored_name)
        with open(file_path, "wb") as f:
            f.write(file.file.read())

        doc = Document(
            subject_id=subject_id,
            title=title,
            file_path=file_path,
            file_size=os.path.getsize(file_path),
            file_type=file_type,
            doc_type=doc_type,
            parse_status="pending",
            year=year,
            question_type=question_type,
        )
        db.add(doc)
        db.commit()
        db.refresh(doc)

        from app.tasks.document_parse import parse_document_task
        parse_document_task.delay(doc.id)
        return doc

    @staticmethod
    def get_document(db: Session, document_id: int) -> Optional[Document]:
        return db.query(Document).filter(Document.id == document_id).first()

    @staticmethod
    def list_documents(
        db: Session,
        page: int = 1,
        size: int = 20,
        subject_id: Optional[int] = None,
        doc_type: Optional[str] = None,
        file_type: Optional[str] = None,
        parse_status: Optional[str] = None,
        keyword: Optional[str] = None,
    ):
        query = db.query(
            Document.id,
            Document.subject_id,
            Subject.name.label("subject_name"),
            Document.title,
            Document.file_path,
            Document.file_size,
            Document.file_type,
            Document.doc_type,
            Document.parse_status,
            Document.error_msg,
            Document.chunk_count,
            Document.year,
            Document.question_type,
            Document.created_at,
            Document.updated_at,
        ).join(Subject, Document.subject_id == Subject.id, isouter=True)

        if subject_id:
            query = query.filter(Document.subject_id == subject_id)
        if doc_type:
            query = query.filter(Document.doc_type == doc_type)
        if file_type:
            query = query.filter(Document.file_type == file_type)
        if parse_status:
            query = query.filter(Document.parse_status == parse_status)
        if keyword:
            query = query.filter(Document.title.like(f"%{keyword}%"))

        total = query.count()
        items = query.order_by(Document.created_at.desc()).offset((page - 1) * size).limit(size).all()

        return items, total

    @staticmethod
    def delete_document(db: Session, document_id: int) -> bool:
        doc = db.query(Document).filter(Document.id == document_id).first()
        if not doc:
            return False

        from app.common.vector_store import delete_document_chunks
        delete_document_chunks(document_id, strict=True)

        file_path = doc.file_path
        neo4j_cleanup = _merge_kg_cleanup(
            _cleanup_document_kg_data(db, document_id),
            _cleanup_orphan_kg_data(db),
        )
        _cancel_document_kg_jobs(db, document_id, delete_records=True)

        db.query(DocumentChunk).filter(DocumentChunk.document_id == document_id).delete()
        db.delete(doc)
        db.commit()

        _sync_document_kg_deletes(db, neo4j_cleanup)

        if file_path and os.path.exists(file_path):
            os.remove(file_path)
        return True

    @staticmethod
    def reparse(db: Session, document_id: int) -> Document:
        doc = db.query(Document).filter(Document.id == document_id).first()
        if not doc:
            raise ValueError("Document not found")

        from app.common.vector_store import delete_document_chunks
        delete_document_chunks(document_id, strict=True)

        doc.parse_revision = (doc.parse_revision or 0) + 1
        neo4j_cleanup = _merge_kg_cleanup(
            _cleanup_document_kg_data(db, document_id),
            _cleanup_orphan_kg_data(db),
        )
        _cancel_document_kg_jobs(db, document_id, delete_records=False)
        db.query(DocumentChunk).filter(DocumentChunk.document_id == document_id).delete()
        doc.parse_status = "pending"
        doc.error_msg = None
        doc.chunk_count = 0
        db.commit()

        _sync_document_kg_deletes(db, neo4j_cleanup)

        from app.tasks.document_parse import parse_document_task
        parse_document_task.delay(document_id)
        return doc

    @staticmethod
    def get_chunks(db: Session, document_id: int):
        return db.query(DocumentChunk).filter(
            DocumentChunk.document_id == document_id
        ).order_by(DocumentChunk.chunk_index).all()

    @staticmethod
    def parse_and_store(db: Session, document_id: int):
        doc = db.query(Document).filter(Document.id == document_id).first()
        if not doc:
            return {"status": "error", "message": "Document not found"}

        try:
            doc.parse_status = "parsing"
            db.commit()

            raw_text = parse_document(doc.file_path, doc.file_type)

            # ── Clean extracted text ──
            from app.common.parsers.cleaner import clean_parsed_text, extract_structure_metadata
            raw_text = clean_parsed_text(raw_text)

            from app.common.kg_settings import get_kg_settings
            kg_settings = get_kg_settings(db)
            min_chunk_chars = kg_settings["chunk.min_chars"]
            if len(raw_text.strip()) < min_chunk_chars:
                doc.parse_status = "success"
                doc.chunk_count = 0
                doc.error_msg = "文档内容过短，跳过解析"
                db.commit()
                return {"status": "skipped", "reason": "content too short"}

            # ── Extract structure metadata for section context ──
            structure = extract_structure_metadata(raw_text)
            sections_map = {}
            for sec in structure.get("sections", []):
                if sec["heading"]:
                    sections_map[sec["heading"]] = sec

            # ── Chunk with structure-aware sizing ──
            from app.common.parsers.chunker import recursive_character_split
            chunk_size = kg_settings["chunk.size"]
            chunk_overlap = kg_settings["chunk.overlap"]

            chunks = recursive_character_split(raw_text, chunk_size=chunk_size, chunk_overlap=chunk_overlap)

            chunks = [c for c in chunks if len(c.strip()) >= min_chunk_chars]
            if not chunks:
                doc.parse_status = "success"
                doc.chunk_count = 0
                db.commit()
                return {"status": "skipped", "reason": "no valid chunks after filtering"}

            # ── Enrich chunks with section context ──
            enriched_chunks = _enrich_chunks_with_context(chunks, structure, doc.title)

            chunk_records = []
            chroma_chunks = []
            for i, chunk_text in enumerate(enriched_chunks):
                chunk = DocumentChunk(
                    document_id=doc.id,
                    chunk_index=i,
                    content=chunk_text,
                    char_count=len(chunk_text),
                )
                db.add(chunk)
                db.flush()
                chunk_records.append(chunk)
                chroma_chunks.append({
                    "id": chunk.id,
                    "document_id": doc.id,
                    "content": chunk_text,
                    "chunk_index": i,
                })

            from app.common.vector_store import add_chunks
            add_chunks(chroma_chunks)

            doc.chunk_count = len(chunks)
            doc.parse_status = "success"
            db.commit()

            from app.tasks.kg_extract import queue_document_extraction_task
            queue_document_extraction_task.delay(document_id)

            return {"status": "success", "chunk_count": len(chunks), "chunk_size": chunk_size}

        except Exception as e:
            db.rollback()
            doc = db.query(Document).filter(Document.id == document_id).first()
            if doc:
                doc.parse_status = "failed"
                doc.error_msg = str(e)[:500]
                db.commit()
            raise e


def _enrich_chunks_with_context(chunks: list, structure: dict, doc_title: str) -> list:
    """Enrich chunk content with document title and section context."""
    if not structure or not structure.get("sections"):
        return chunks

    sections = structure["sections"]

    enriched = []
    for chunk in chunks:
        prefix_parts = []

        # Find which section this chunk belongs to
        best_section = None
        best_overlap = 0
        for sec in sections:
            if not sec.get("content"):
                continue
            # Simple overlap: count common words
            chunk_words = set(chunk[:200].split())
            sec_words = set(sec["content"][:200].split())
            overlap = len(chunk_words & sec_words)
            if overlap > best_overlap:
                best_overlap = overlap
                best_section = sec

        if best_section and best_section.get("heading"):
            prefix_parts.append(f"[{doc_title} > {best_section['heading']}]")

        if prefix_parts:
            enriched.append("\n".join(prefix_parts) + "\n" + chunk)
        else:
            enriched.append(chunk)

    return enriched


def _cancel_document_kg_jobs(db: Session, document_id: int, delete_records: bool = False):
    run_ids = [
        row.id for row in db.query(KgExtractionRun.id)
        .filter(KgExtractionRun.document_id == document_id)
        .all()
    ]
    if not run_ids:
        return

    if delete_records:
        db.query(KgExtractionBatch).filter(
            or_(
                KgExtractionBatch.run_id.in_(run_ids),
                KgExtractionBatch.document_id == document_id,
            )
        ).delete(synchronize_session=False)
        db.query(KgExtractionRun).filter(KgExtractionRun.id.in_(run_ids)).delete(synchronize_session=False)
        return

    db.query(KgExtractionBatch).filter(
        or_(
            KgExtractionBatch.run_id.in_(run_ids),
            KgExtractionBatch.document_id == document_id,
        ),
        KgExtractionBatch.status.in_(("queued", "dispatched", "running")),
    ).update({"status": "stale"}, synchronize_session=False)
    db.query(KgExtractionRun).filter(
        KgExtractionRun.id.in_(run_ids),
        KgExtractionRun.status.in_(("queued", "running")),
    ).update({"status": "canceled"}, synchronize_session=False)


def _cleanup_document_kg_data(db: Session, document_id: int) -> dict:
    point_ids = {
        row.knowledge_point_id for row in db.query(KnowledgePointSource.knowledge_point_id)
        .filter(KnowledgePointSource.document_id == document_id)
        .all()
    }
    direct_relation_ids = {
        row.relation_id for row in db.query(KnowledgeRelationEvidence.relation_id)
        .filter(
            KnowledgeRelationEvidence.document_id == document_id,
            KnowledgeRelationEvidence.relation_id.isnot(None),
        )
        .all()
    }

    db.query(KnowledgeRelationCandidate).filter(
        KnowledgeRelationCandidate.document_id == document_id
    ).delete(synchronize_session=False)
    db.query(KnowledgeRelationEvidence).filter(
        KnowledgeRelationEvidence.document_id == document_id
    ).delete(synchronize_session=False)
    db.query(KnowledgePointSource).filter(
        KnowledgePointSource.document_id == document_id
    ).delete(synchronize_session=False)

    orphan_point_ids = set()
    for point_id in point_ids:
        remaining_source = db.query(KnowledgePointSource.id).filter(
            KnowledgePointSource.knowledge_point_id == point_id
        ).first()
        point = db.query(KnowledgePoint).filter(KnowledgePoint.id == point_id).first()
        if point and point.origin != "manual" and not remaining_source:
            orphan_point_ids.add(point_id)

    relation_ids_to_delete = set()
    for relation_id in direct_relation_ids:
        remaining_evidence = db.query(KnowledgeRelationEvidence.id).filter(
            KnowledgeRelationEvidence.relation_id == relation_id
        ).first()
        relation = db.query(KnowledgeRelation).filter(KnowledgeRelation.id == relation_id).first()
        if relation and relation.origin != "manual" and not remaining_evidence:
            relation_ids_to_delete.add(relation_id)

    if orphan_point_ids:
        attached_relation_ids = {
            row.id for row in db.query(KnowledgeRelation.id)
            .filter(
                or_(
                    KnowledgeRelation.source_node_id.in_(orphan_point_ids),
                    KnowledgeRelation.target_node_id.in_(orphan_point_ids),
                )
            )
            .all()
        }
        relation_ids_to_delete.update(attached_relation_ids)
        db.query(KnowledgeRelationCandidate).filter(
            or_(
                KnowledgeRelationCandidate.source_node_id.in_(orphan_point_ids),
                KnowledgeRelationCandidate.target_node_id.in_(orphan_point_ids),
            )
        ).delete(synchronize_session=False)

    relation_payloads = []
    if relation_ids_to_delete:
        relations = db.query(KnowledgeRelation).filter(
            KnowledgeRelation.id.in_(relation_ids_to_delete)
        ).all()
        relation_payloads = [
            {
                "id": relation.id,
                "source_id": relation.source_node_id,
                "target_id": relation.target_node_id,
                "relation_type": relation.relation_type,
            }
            for relation in relations
        ]
        db.query(KnowledgeRelationEvidence).filter(
            KnowledgeRelationEvidence.relation_id.in_(relation_ids_to_delete)
        ).delete(synchronize_session=False)
        db.query(KnowledgeRelation).filter(
            KnowledgeRelation.id.in_(relation_ids_to_delete)
        ).delete(synchronize_session=False)

    if orphan_point_ids:
        db.query(KnowledgePoint).filter(
            KnowledgePoint.id.in_(orphan_point_ids)
        ).delete(synchronize_session=False)

    return {
        "relations": relation_payloads,
        "points": sorted(orphan_point_ids),
    }


def _cleanup_orphan_kg_data(db: Session) -> dict:
    active_point_source = exists().where(
        KnowledgePointSource.knowledge_point_id == KnowledgePoint.id,
        KnowledgePointSource.document_id == Document.id,
    )
    orphan_points = db.query(KnowledgePoint).filter(
        KnowledgePoint.origin != "manual",
        ~active_point_source,
    ).all()
    orphan_point_ids = {point.id for point in orphan_points}

    active_relation_evidence = exists().where(
        KnowledgeRelationEvidence.relation_id == KnowledgeRelation.id,
        KnowledgeRelationEvidence.document_id == Document.id,
    )
    source_point_exists = exists().where(KnowledgePoint.id == KnowledgeRelation.source_node_id)
    target_point_exists = exists().where(KnowledgePoint.id == KnowledgeRelation.target_node_id)
    stale_relation_filters = [~active_relation_evidence]
    if orphan_point_ids:
        stale_relation_filters.append(or_(
            KnowledgeRelation.source_node_id.in_(orphan_point_ids),
            KnowledgeRelation.target_node_id.in_(orphan_point_ids),
        ))
    orphan_relations = db.query(KnowledgeRelation).filter(
        or_(
            and_(KnowledgeRelation.origin != "manual", or_(*stale_relation_filters)),
            ~source_point_exists,
            ~target_point_exists,
        ),
    ).all()
    relation_ids = {relation.id for relation in orphan_relations}
    relation_payloads = [
        {
            "id": relation.id,
            "source_id": relation.source_node_id,
            "target_id": relation.target_node_id,
            "relation_type": relation.relation_type,
        }
        for relation in orphan_relations
    ]

    if relation_ids:
        db.query(KnowledgeRelationEvidence).filter(
            KnowledgeRelationEvidence.relation_id.in_(relation_ids)
        ).delete(synchronize_session=False)
        db.query(KnowledgeRelation).filter(
            KnowledgeRelation.id.in_(relation_ids)
        ).delete(synchronize_session=False)

    if orphan_point_ids:
        db.query(KnowledgeRelationCandidate).filter(
            or_(
                KnowledgeRelationCandidate.source_node_id.in_(orphan_point_ids),
                KnowledgeRelationCandidate.target_node_id.in_(orphan_point_ids),
            )
        ).delete(synchronize_session=False)
        db.query(KnowledgePointSource).filter(
            KnowledgePointSource.knowledge_point_id.in_(orphan_point_ids)
        ).delete(synchronize_session=False)
        db.query(KnowledgePoint).filter(
            KnowledgePoint.id.in_(orphan_point_ids)
        ).delete(synchronize_session=False)

    return {
        "relations": relation_payloads,
        "points": sorted(orphan_point_ids),
    }


def _merge_kg_cleanup(*cleanups: dict) -> dict:
    relations = {}
    points = set()
    for cleanup in cleanups:
        for relation in cleanup.get("relations", []):
            relation_id = relation.get("id")
            if relation_id is not None:
                relations[relation_id] = relation
        points.update(cleanup.get("points", []))
    return {
        "relations": list(relations.values()),
        "points": sorted(points),
    }


def _sync_document_kg_deletes(db: Session, cleanup: dict):
    from app.common.graph_store import (
        delete_node as neo4j_delete_node,
        delete_relation as neo4j_delete_relation,
        prune_graph as neo4j_prune_graph,
    )

    for relation in cleanup.get("relations", []):
        try:
            neo4j_delete_relation(
                relation["source_id"],
                relation["target_id"],
                relation["relation_type"],
            )
        except Exception as exc:
            _record_kg_sync_failure(
                db,
                "delete",
                "relation",
                relation.get("id"),
                relation,
                exc,
            )

    for point_id in cleanup.get("points", []):
        try:
            neo4j_delete_node(point_id)
        except Exception as exc:
            _record_kg_sync_failure(db, "delete", "node", point_id, {"id": point_id}, exc)

    try:
        node_ids = [row.id for row in db.query(KnowledgePoint.id).all()]
        relations = [
            {
                "source_id": row.source_node_id,
                "target_id": row.target_node_id,
                "relation_type": row.relation_type,
            }
            for row in db.query(
                KnowledgeRelation.source_node_id,
                KnowledgeRelation.target_node_id,
                KnowledgeRelation.relation_type,
            ).all()
        ]
        neo4j_prune_graph(node_ids, relations)
    except Exception as exc:
        _record_kg_sync_failure(
            db,
            "prune",
            "graph",
            None,
            {"reason": "align neo4j graph with mysql knowledge graph"},
            exc,
        )


def _record_kg_sync_failure(
    db: Session,
    operation: str,
    entity_type: str,
    entity_id: Optional[int],
    payload: dict,
    error: Exception,
):
    try:
        db.add(KgSyncFailure(
            operation=operation,
            entity_type=entity_type,
            entity_id=entity_id,
            payload=payload,
            error_msg=str(error)[:1000],
        ))
        db.commit()
    except Exception:
        db.rollback()
