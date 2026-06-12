import os
import time
from datetime import datetime
from typing import Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.common.graph_store import (
    create_node as neo4j_create_node,
    create_relation as neo4j_create_relation,
    delete_node as neo4j_delete_node,
    delete_relation as neo4j_delete_relation,
    get_search_subgraph as neo4j_get_search_subgraph,
    get_subgraph as neo4j_get_subgraph,
    search_nodes as neo4j_search_nodes,
    update_node as neo4j_update_node,
)
from app.common.llm_client import chat
from app.config import settings
from app.models import (
    Document, KgExtractionBatch, KgExtractionRun, KgRebuild, KgSyncFailure, KnowledgePoint,
    KnowledgePointSource, KnowledgeRelation, KnowledgeRelationCandidate, KnowledgeRelationEvidence, Subject,
)


def _record_sync_failure(db: Session, operation: str, entity_type: str, entity_id: int, payload: dict, error: Exception):
    db.add(KgSyncFailure(
        operation=operation,
        entity_type=entity_type,
        entity_id=entity_id,
        payload=payload,
        error_msg=str(error)[:1000],
    ))
    db.commit()


class KgService:

    @staticmethod
    def create_point(db: Session, name: str, subject_id: int, description: str = None, difficulty: int = 3) -> KnowledgePoint:
        point = KnowledgePoint(
            name=name, subject_id=subject_id, description=description, difficulty=difficulty,
            origin="manual", confidence=1.0, review_status="approved",
        )
        db.add(point)
        db.commit()
        db.refresh(point)

        try:
            neo4j_create_node(point.id, point.name, point.subject_id)
        except Exception as exc:
            _record_sync_failure(db, "upsert", "node", point.id, {"name": point.name}, exc)

        return point

    @staticmethod
    def update_point(db: Session, point_id: int, name: str = None, description: str = None, difficulty: int = None) -> Optional[KnowledgePoint]:
        point = db.query(KnowledgePoint).filter(KnowledgePoint.id == point_id).first()
        if not point:
            return None
        if name is not None:
            point.name = name
        if description is not None:
            point.description = description
        if difficulty is not None:
            point.difficulty = difficulty
        db.commit()
        db.refresh(point)

        try:
            neo4j_update_node(point.id, point.name, point.description)
        except Exception as exc:
            _record_sync_failure(db, "upsert", "node", point.id, {"name": point.name}, exc)

        return point

    @staticmethod
    def delete_point(db: Session, point_id: int) -> bool:
        point = db.query(KnowledgePoint).filter(KnowledgePoint.id == point_id).first()
        if not point:
            return False
        relation_ids = [
            row.id for row in db.query(KnowledgeRelation.id).filter(
                (KnowledgeRelation.source_node_id == point_id) | (KnowledgeRelation.target_node_id == point_id)
            ).all()
        ]
        if relation_ids:
            db.query(KnowledgeRelationEvidence).filter(
                KnowledgeRelationEvidence.relation_id.in_(relation_ids)
            ).delete(synchronize_session=False)
        db.query(KnowledgeRelationCandidate).filter(
            (KnowledgeRelationCandidate.source_node_id == point_id) |
            (KnowledgeRelationCandidate.target_node_id == point_id)
        ).delete(synchronize_session=False)
        db.query(KnowledgePointSource).filter(
            KnowledgePointSource.knowledge_point_id == point_id
        ).delete(synchronize_session=False)
        db.query(KnowledgeRelation).filter(
            (KnowledgeRelation.source_node_id == point_id) | (KnowledgeRelation.target_node_id == point_id)
        ).delete(synchronize_session=False)
        db.delete(point)
        db.commit()

        try:
            neo4j_delete_node(point_id)
        except Exception as exc:
            _record_sync_failure(db, "delete", "node", point_id, {}, exc)

        return True

    @staticmethod
    def list_points(db: Session, subject_id: int = None, keyword: str = None, page: int = 1, size: int = 20):
        query = db.query(KnowledgePoint)
        if subject_id:
            query = query.filter(KnowledgePoint.subject_id == subject_id)
        if keyword:
            query = query.filter(KnowledgePoint.name.like(f"%{keyword}%"))
        total = query.count()
        items = query.order_by(KnowledgePoint.id).offset((page - 1) * size).limit(size).all()
        return items, total

    @staticmethod
    def get_point(db: Session, point_id: int) -> Optional[KnowledgePoint]:
        return db.query(KnowledgePoint).filter(KnowledgePoint.id == point_id).first()

    @staticmethod
    def create_relation(db: Session, source_id: int, target_id: int, relation_type: str, description: str = None) -> Optional[KnowledgeRelation]:
        source = db.query(KnowledgePoint).filter(KnowledgePoint.id == source_id).first()
        target = db.query(KnowledgePoint).filter(KnowledgePoint.id == target_id).first()
        if not source or not target or source.id == target.id or source.subject_id != target.subject_id:
            return None

        existing = db.query(KnowledgeRelation).filter(
            KnowledgeRelation.source_node_id == source_id,
            KnowledgeRelation.target_node_id == target_id,
            KnowledgeRelation.relation_type == relation_type,
        ).first()
        if existing:
            try:
                neo4j_create_node(source.id, source.name, source.subject_id)
                neo4j_create_node(target.id, target.name, target.subject_id)
                neo4j_create_relation(source_id, target_id, relation_type, description or existing.description)
            except Exception as exc:
                _record_sync_failure(db, "upsert", "relation", existing.id, {}, exc)
            return existing

        rel = KnowledgeRelation(
            source_node_id=source_id,
            target_node_id=target_id,
            relation_type=relation_type,
            description=description,
            origin="manual",
            confidence=1.0,
            review_status="approved",
        )
        db.add(rel)
        db.commit()
        db.refresh(rel)

        try:
            neo4j_create_node(source.id, source.name, source.subject_id)
            neo4j_create_node(target.id, target.name, target.subject_id)
            neo4j_create_relation(source_id, target_id, relation_type, description)
        except Exception as exc:
            _record_sync_failure(db, "upsert", "relation", rel.id, {}, exc)

        return rel

    @staticmethod
    def update_relation(
        db: Session,
        relation_id: int,
        source_id: int,
        target_id: int,
        relation_type: str,
        description: str = None,
    ) -> Optional[KnowledgeRelation]:
        rel = db.query(KnowledgeRelation).filter(KnowledgeRelation.id == relation_id).first()
        source = db.query(KnowledgePoint).filter(KnowledgePoint.id == source_id).first()
        target = db.query(KnowledgePoint).filter(KnowledgePoint.id == target_id).first()
        if not rel or not source or not target or source.id == target.id or source.subject_id != target.subject_id:
            return None

        old_payload = {
            "source_id": rel.source_node_id,
            "target_id": rel.target_node_id,
            "relation_type": rel.relation_type,
        }
        rel.source_node_id = source_id
        rel.target_node_id = target_id
        rel.relation_type = relation_type
        rel.description = description
        rel.origin = "manual"
        rel.review_status = "approved"
        db.commit()
        db.refresh(rel)

        try:
            neo4j_delete_relation(
                old_payload["source_id"],
                old_payload["target_id"],
                old_payload["relation_type"],
            )
            neo4j_create_node(source.id, source.name, source.subject_id)
            neo4j_create_node(target.id, target.name, target.subject_id)
            neo4j_create_relation(source_id, target_id, relation_type, description)
        except Exception as exc:
            _record_sync_failure(db, "upsert", "relation", rel.id, {
                "old": old_payload,
                "source_id": source_id,
                "target_id": target_id,
                "relation_type": relation_type,
                "description": description,
            }, exc)

        return rel

    @staticmethod
    def delete_relation(db: Session, relation_id: int) -> bool:
        rel = db.query(KnowledgeRelation).filter(KnowledgeRelation.id == relation_id).first()
        if not rel:
            return False
        payload = {
            "source_id": rel.source_node_id,
            "target_id": rel.target_node_id,
            "relation_type": rel.relation_type,
        }
        db.query(KnowledgeRelationEvidence).filter(
            KnowledgeRelationEvidence.relation_id == relation_id
        ).delete(synchronize_session=False)
        db.delete(rel)
        db.commit()

        try:
            neo4j_delete_relation(payload["source_id"], payload["target_id"], payload["relation_type"])
        except Exception as exc:
            _record_sync_failure(db, "delete", "relation", relation_id, payload, exc)

        return True

    @staticmethod
    def list_relations(db: Session, subject_id: int = None) -> list:
        query = db.query(KnowledgeRelation)
        if subject_id:
            query = query.join(
                KnowledgePoint,
                KnowledgeRelation.source_node_id == KnowledgePoint.id,
            ).filter(KnowledgePoint.subject_id == subject_id)
        return query.all()

    @staticmethod
    def rebuild_status(db: Session) -> dict:
        rebuild = db.query(KgRebuild).order_by(KgRebuild.id.desc()).first()
        if not rebuild:
            return {"status": "not_started", "total_documents": 0, "completed_documents": 0, "failed_documents": 0}
        failed_runs = (
            db.query(KgExtractionRun)
            .filter(KgExtractionRun.rebuild_id == rebuild.id, KgExtractionRun.status == "failed")
            .order_by(KgExtractionRun.id.desc())
            .limit(10)
            .all()
        )
        runs = db.query(KgExtractionRun).filter(
            KgExtractionRun.rebuild_id == rebuild.id,
            KgExtractionRun.status != "canceled",
        ).all()
        run_ids = [run.id for run in runs]
        batches = db.query(KgExtractionBatch).filter(KgExtractionBatch.run_id.in_(run_ids)).all() if run_ids else []
        batch_map = {}
        for batch in batches:
            batch_map.setdefault(batch.run_id, []).append(batch)
        total_chunks = sum(max(0, batch.end_index - batch.start_index) for batch in batches)
        processed_chunks = sum(
            max(0, batch.end_index - batch.start_index)
            for batch in batches if batch.status in {"success", "failed", "stale"}
        )
        elapsed_seconds = max(1, int((datetime.now() - rebuild.started_at).total_seconds())) if rebuild.started_at else 0
        eta_seconds = int((total_chunks - processed_chunks) / (processed_chunks / elapsed_seconds)) if processed_chunks else None
        documents = []
        for run in runs:
            run_batches = batch_map.get(run.id, [])
            run_total = sum(max(0, batch.end_index - batch.start_index) for batch in run_batches)
            run_processed = sum(
                max(0, batch.end_index - batch.start_index)
                for batch in run_batches if batch.status in {"success", "failed", "stale"}
            )
            documents.append({
                "document_id": run.document_id,
                "title": db.query(Document.title).filter(Document.id == run.document_id).scalar() or "",
                "status": run.status,
                "processed_chunks": run_processed,
                "total_chunks": run_total,
                "percentage": round(run_processed * 100 / run_total) if run_total else 0,
                "failed_batches": sum(batch.status == "failed" for batch in run_batches),
            })
        return {
            "id": rebuild.id,
            "version": rebuild.version,
            "status": rebuild.status,
            "total_documents": rebuild.total_documents,
            "completed_documents": rebuild.completed_documents,
            "failed_documents": rebuild.failed_documents,
            "created_at": rebuild.created_at.isoformat() if rebuild.created_at else None,
            "finished_at": rebuild.finished_at.isoformat() if rebuild.finished_at else None,
            "failed_runs": [{"document_id": run.document_id, "error_msg": run.error_msg} for run in failed_runs],
            "processed_chunks": processed_chunks,
            "total_chunks": total_chunks,
            "percentage": round(processed_chunks * 100 / total_chunks) if total_chunks else 0,
            "eta_seconds": max(0, eta_seconds) if eta_seconds is not None else None,
            "documents": documents,
            "total_nodes": db.query(KnowledgePoint).count(),
        }

    @staticmethod
    def retry_failed_rebuild_documents(db: Session) -> int:
        rebuild = db.query(KgRebuild).order_by(KgRebuild.id.desc()).first()
        if not rebuild:
            return 0
        runs = db.query(KgExtractionRun).filter(
            KgExtractionRun.rebuild_id == rebuild.id,
            KgExtractionRun.status == "failed",
        ).all()
        from app.tasks.kg_extract import queue_document_extraction_task
        for run in runs:
            run.status = "queued"
            run.error_msg = None
            run.processed_batches = 0
            db.query(KgExtractionBatch).filter(KgExtractionBatch.run_id == run.id).delete()
            db.commit()
            queue_document_extraction_task.delay(run.document_id, run.id)
        if runs:
            rebuild.status = "running"
            rebuild.finished_at = None
            db.commit()
        return len(runs)

    @staticmethod
    def list_relation_candidates(db: Session, status: str = "pending", page: int = 1, size: int = 20):
        query = (
            db.query(
                KnowledgeRelationCandidate,
                KnowledgePoint.name.label("source_name"),
                Document.title.label("document_title"),
            )
            .join(KnowledgePoint, KnowledgeRelationCandidate.source_node_id == KnowledgePoint.id)
            .outerjoin(Document, KnowledgeRelationCandidate.document_id == Document.id)
            .filter(KnowledgeRelationCandidate.status == status)
        )
        total = query.count()
        rows = query.order_by(KnowledgeRelationCandidate.id.desc()).offset((page - 1) * size).limit(size).all()
        items = []
        for candidate, source_name, document_title in rows:
            target = db.query(KnowledgePoint).filter(KnowledgePoint.id == candidate.target_node_id).first()
            items.append({
                "id": candidate.id,
                "source_node_id": candidate.source_node_id,
                "source_name": source_name,
                "target_node_id": candidate.target_node_id,
                "target_name": target.name if target else "",
                "relation_type": candidate.relation_type,
                "description": candidate.description,
                "evidence_text": candidate.evidence_text,
                "confidence": float(candidate.confidence),
                "document_id": candidate.document_id,
                "document_title": document_title,
                "status": candidate.status,
            })
        return items, total

    @staticmethod
    def review_relation_candidate(db: Session, candidate_id: int, approved: bool, user_id: int) -> bool:
        candidate = db.query(KnowledgeRelationCandidate).filter(
            KnowledgeRelationCandidate.id == candidate_id,
            KnowledgeRelationCandidate.status == "pending",
        ).first()
        if not candidate:
            return False
        candidate.status = "approved" if approved else "rejected"
        candidate.reviewed_by = user_id
        candidate.reviewed_at = datetime.now()
        if approved:
            relation = KgService.create_relation(
                db,
                candidate.source_node_id,
                candidate.target_node_id,
                candidate.relation_type,
                candidate.description,
            )
            if relation:
                relation.origin = "auto"
                relation.confidence = candidate.confidence
                relation.review_status = "approved"
                db.add(KnowledgeRelationEvidence(
                    relation_id=relation.id,
                    document_id=candidate.document_id,
                    chunk_id=candidate.chunk_id,
                    source_name=db.query(KnowledgePoint.name).filter(KnowledgePoint.id == candidate.source_node_id).scalar() or "",
                    target_name=db.query(KnowledgePoint.name).filter(KnowledgePoint.id == candidate.target_node_id).scalar() or "",
                    relation_type=candidate.relation_type,
                    evidence_text=candidate.evidence_text,
                    confidence=candidate.confidence,
                    prompt_version=candidate.prompt_version,
                ))
        db.commit()
        return True

    @staticmethod
    def get_subgraph(
        db: Session,
        subject_id: int = None,
        depth: int = 2,
        offset: int = 0,
        size: int = 600,
    ) -> dict:
        return KgService._mysql_subgraph(db, subject_id, offset, size)

    @staticmethod
    def search_subgraph(db: Session, keyword: str, subject_id: int = None) -> dict:
        neo4j_error = None
        try:
            data = neo4j_get_search_subgraph(keyword, subject_id, depth=1)
            if data.get("nodes") or data.get("edges"):
                return KgService._attach_mysql_relation_ids(db, data, subject_id)
        except Exception as e:
            neo4j_error = str(e)
        data = KgService._mysql_search_subgraph(db, keyword, subject_id)
        if neo4j_error:
            data["warning"] = f"Neo4j 查询失败，已使用 MySQL 兜底：{neo4j_error}"
        return data

    @staticmethod
    def search(db: Session, keyword: str, subject_id: int = None) -> list:
        try:
            results = neo4j_search_nodes(keyword, subject_id)
            if results:
                return results
        except Exception:
            pass
        query = db.query(KnowledgePoint)
        if subject_id:
            query = query.filter(KnowledgePoint.subject_id == subject_id)
        return [
            {"id": point.id, "name": point.name, "subject_id": point.subject_id}
            for point in query.filter(KnowledgePoint.name.like(f"%{keyword.strip()}%")).limit(50).all()
        ]

    @staticmethod
    def _node_payload(point: KnowledgePoint) -> dict:
        return {
            "id": point.id,
            "label": point.name,
            "subject_id": point.subject_id,
            "group": str(point.subject_id or 0),
        }

    @staticmethod
    def _edge_payload(rel: KnowledgeRelation) -> dict:
        return {
            "id": rel.id,
            "from": rel.source_node_id,
            "to": rel.target_node_id,
            "label": rel.relation_type,
            "title": rel.description or rel.relation_type,
            "description": rel.description,
        }

    @staticmethod
    def _attach_mysql_relation_ids(db: Session, data: dict, subject_id: int = None) -> dict:
        """Neo4j is the graph query layer, but MySQL relation IDs drive editing."""
        edges = data.get("edges") or []
        node_ids = {
            value
            for edge in edges
            for value in (edge.get("from"), edge.get("to"))
            if value is not None
        }
        if not node_ids:
            return data

        query = db.query(KnowledgeRelation).filter(
            KnowledgeRelation.source_node_id.in_(node_ids),
            KnowledgeRelation.target_node_id.in_(node_ids),
        )
        if subject_id:
            query = query.join(
                KnowledgePoint,
                KnowledgeRelation.source_node_id == KnowledgePoint.id,
            ).filter(KnowledgePoint.subject_id == subject_id)

        exact_map = {}
        type_map = {}
        for rel in query.all():
            rel_type = rel.relation_type or ""
            rel_desc = rel.description or ""
            exact_map.setdefault((rel.source_node_id, rel.target_node_id, rel_type, rel_desc), rel.id)
            type_map.setdefault((rel.source_node_id, rel.target_node_id, rel_type), rel.id)

        normalized_edges = []
        seen_ids = set()
        for idx, edge in enumerate(edges):
            rel_type = edge.get("label") or edge.get("relation_type") or ""
            rel_desc = edge.get("description") or edge.get("title") or ""
            source_id = edge.get("from")
            target_id = edge.get("to")
            mysql_id = exact_map.get((source_id, target_id, rel_type, rel_desc))
            if mysql_id is None:
                mysql_id = type_map.get((source_id, target_id, rel_type))

            normalized = dict(edge)
            normalized["relation_type"] = rel_type
            normalized["description"] = rel_desc
            if mysql_id is not None:
                normalized["id"] = mysql_id
            elif normalized.get("id") is None:
                normalized["id"] = f"neo4j:{normalized.get('neo4j_rel_id', idx)}"

            dedup_key = normalized["id"]
            if dedup_key in seen_ids:
                dedup_key = f"{dedup_key}:{idx}"
                normalized["id"] = dedup_key
            seen_ids.add(dedup_key)
            normalized_edges.append(normalized)

        data["edges"] = normalized_edges
        return data

    @staticmethod
    def _mysql_subgraph(db: Session, subject_id: int = None, offset: int = 0, size: int = 600) -> dict:
        point_query = db.query(KnowledgePoint)
        if subject_id:
            point_query = point_query.filter(KnowledgePoint.subject_id == subject_id)
        total_nodes = point_query.count()
        points = point_query.order_by(KnowledgePoint.id).offset(offset).limit(size).all()
        point_ids = {point.id for point in points}

        rel_query = db.query(KnowledgeRelation)
        if subject_id:
            rel_query = rel_query.join(
                KnowledgePoint,
                KnowledgeRelation.source_node_id == KnowledgePoint.id,
            ).filter(KnowledgePoint.subject_id == subject_id)
        total_edges = rel_query.count()
        relations = []
        if point_ids:
            relations = rel_query.filter(
                KnowledgeRelation.source_node_id.in_(point_ids),
                KnowledgeRelation.target_node_id.in_(point_ids),
            ).order_by(KnowledgeRelation.id).all()
        next_offset = offset + len(points)
        return {
            "nodes": [KgService._node_payload(point) for point in points],
            "edges": [KgService._edge_payload(rel) for rel in relations],
            "total_nodes": total_nodes,
            "total_edges": total_edges,
            "offset": offset,
            "size": size,
            "next_offset": next_offset,
            "has_more": next_offset < total_nodes,
        }

    @staticmethod
    def _mysql_search_subgraph(db: Session, keyword: str, subject_id: int = None) -> dict:
        keyword = (keyword or "").strip()
        if not keyword:
            return {"nodes": [], "edges": []}

        point_query = db.query(KnowledgePoint)
        if subject_id:
            point_query = point_query.filter(KnowledgePoint.subject_id == subject_id)
        matched_points = point_query.filter(KnowledgePoint.name.like(f"%{keyword}%")).all()
        if matched_points:
            return {
                "nodes": [KgService._node_payload(point) for point in matched_points],
                "edges": [],
            }

        rel_query = db.query(KnowledgeRelation)
        if subject_id:
            rel_query = rel_query.join(
                KnowledgePoint,
                KnowledgeRelation.source_node_id == KnowledgePoint.id,
            ).filter(KnowledgePoint.subject_id == subject_id)
        matched_relations = rel_query.filter(or_(
            KnowledgeRelation.relation_type.like(f"%{keyword}%"),
            KnowledgeRelation.description.like(f"%{keyword}%"),
        )).all()

        point_ids = {point.id for point in matched_points}
        for rel in matched_relations:
            point_ids.add(rel.source_node_id)
            point_ids.add(rel.target_node_id)

        if not point_ids:
            return {"nodes": [], "edges": []}

        visible_points = db.query(KnowledgePoint).filter(KnowledgePoint.id.in_(point_ids)).all()

        return {
            "nodes": [KgService._node_payload(point) for point in visible_points],
            "edges": [KgService._edge_payload(rel) for rel in matched_relations],
        }

    @staticmethod
    def generate_document(db: Session, subject_id: int, doc_type: str) -> Document:
        subject = db.query(Subject).filter(Subject.id == subject_id).first()
        if not subject:
            raise ValueError("科目不存在")

        kg_data = neo4j_get_subgraph(subject_id)
        nodes = kg_data.get("nodes", [])
        edges = kg_data.get("edges", [])

        from app.common.vector_store import search_chunks
        chunk_results = search_chunks(subject.name, top_k=30, where={"subject_id": subject_id})

        nodes_text = "\n".join(
            f"- {n.get('label', '')} (ID: {n.get('id', '')})"
            for n in nodes[:50]
        ) if nodes else "暂无知识点"

        edges_text = "\n".join(
            f"- {e.get('from', '')} --[{e.get('label', '')}]--> {e.get('to', '')}"
            for e in edges[:80]
        ) if edges else "暂无关系"

        chunks_text = "\n\n".join(
            c.get("content", "") for c in chunk_results[:15]
        ) if chunk_results else "暂无相关文档内容"

        doc_type_labels = {
            "study_guide": ("学习指南", "supplement"),
            "exam_paper": ("考试试卷", "exam"),
            "summary": ("知识总结", "note"),
            "outline": ("教学大纲", "textbook"),
        }
        label, db_doc_type = doc_type_labels.get(doc_type, ("学习指南", "supplement"))

        system_prompt = """你是一个专业的教育文档生成助手。
根据提供的知识图谱（知识点和关系）以及相关文档内容，生成一份结构清晰、内容详实的Markdown文档。
文档应当包含：
1. 标题和概述
2. 知识结构（按关系组织，体现知识点之间的关联）
3. 每个知识点的详细说明
4. 总结或思考题

要求：
- 使用中文
- 使用Markdown格式（标题、列表、表格、代码块等）
- 内容专业、准确
- 不少于1000字"""

        user_prompt = f"""请为科目「{subject.name}」生成一份{label}。

## 知识图谱数据

### 知识点（共{len(nodes)}个）
{nodes_text}

### 知识点关系（共{len(edges)}条）
{edges_text}

## 相关文档内容
{chunks_text}

请基于以上知识图谱和文档内容，生成一份结构完整的{label}。"""

        content = chat(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.7,
            max_tokens=8192,
        )

        title = f"{subject.name}{label}"
        file_type = "md"
        subject_dir = os.path.join(settings.upload_dir, str(subject_id))
        os.makedirs(subject_dir, exist_ok=True)

        timestamp = int(time.time())
        filename = f"kg_gen_{doc_type}_{timestamp}.md"
        file_path = os.path.join(subject_dir, filename)

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)

        doc = Document(
            subject_id=subject_id,
            title=title,
            file_path=file_path,
            file_size=os.path.getsize(file_path),
            file_type=file_type,
            doc_type=db_doc_type,
            parse_status="pending",
        )
        db.add(doc)
        db.commit()
        db.refresh(doc)

        from app.tasks.document_parse import parse_document_task
        parse_document_task.delay(doc.id)

        return doc
