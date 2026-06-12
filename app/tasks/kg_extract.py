import json
import re
import unicodedata
from datetime import datetime, timedelta

from sqlalchemy import and_, exists, or_

from app.common.graph_store import (
    create_node as neo4j_create_node,
    create_relation as neo4j_create_relation,
    run_query,
)
from app.common.kg_local_extractor import extract_local_knowledge
from app.common.llm_client import chat
from app.database import SessionLocal
from app.config import settings
from app.models import (
    Document, DocumentChunk, KgExtractionBatch, KgExtractionRun, KgRebuild, KgSyncFailure,
    KnowledgePoint, KnowledgePointSource, KnowledgeRelation,
    KnowledgeRelationCandidate, KnowledgeRelationEvidence, Subject,
)
from app.tasks.celery_app import celery_app

BATCH_SIZE = 1
MAX_CHARS_PER_CHUNK = 1200
GLOBAL_REL_WINDOW_SIZE = 80
GLOBAL_REL_WINDOW_OVERLAP = 10
PROMPT_VERSION = "kg-v3-physical-semantic"
VALID_RELATION_TYPES = {
    "PREREQUISITE", "NEXT", "RELATED", "CONTAINS", "CONTRAST", "EXAMINED_IN",
}


@celery_app.task(name="kg_task.queue_document_extraction")
def queue_document_extraction_task(document_id: int, run_id: int = None):
    """Create resumable extraction batches for one parsed document."""
    db = SessionLocal()
    try:
        doc = db.query(Document).filter(Document.id == document_id).first()
        if not doc or doc.parse_status != "success":
            return {"status": "skipped", "reason": "document not parsed successfully"}
        if not run_id:
            from app.common.schema_migrations import KG_REBUILD_VERSION
            existing_run = db.query(KgExtractionRun).filter(
                KgExtractionRun.document_id == document_id,
                KgExtractionRun.version == KG_REBUILD_VERSION,
                KgExtractionRun.status.in_(("queued", "running")),
            ).order_by(KgExtractionRun.id.desc()).first()
            if existing_run:
                return {"status": "skipped", "reason": "active run already exists", "run_id": existing_run.id}
            run = KgExtractionRun(document_id=document_id, version=KG_REBUILD_VERSION, status="queued")
            db.add(run)
            db.commit()
            db.refresh(run)
        else:
            run = db.query(KgExtractionRun).filter(KgExtractionRun.id == run_id).first()
        if not run or run.status == "canceled":
            return {"status": "skipped", "reason": "run canceled"}

        from app.common.kg_settings import get_kg_settings
        batch_chunks = get_kg_settings(db)["kg.batch_chunks"]
        total_chunks = db.query(DocumentChunk).filter(DocumentChunk.document_id == document_id).count()
        if not total_chunks:
            run.status = "failed"
            run.error_msg = "no chunks"
            run.finished_at = datetime.now()
            db.commit()
            _update_rebuild_status(db, run.rebuild_id)
            return {"status": "skipped", "reason": "no chunks"}

        run.status = "running"
        run.model = settings.llm_model
        run.started_at = run.started_at or datetime.now()
        run.batch_count = (total_chunks + batch_chunks - 1) // batch_chunks
        db.commit()

        existing = db.query(KgExtractionBatch).filter(KgExtractionBatch.run_id == run.id).count()
        if not existing:
            for start in range(0, total_chunks, batch_chunks):
                db.add(KgExtractionBatch(
                    run_id=run.id,
                    document_id=document_id,
                    parse_revision=doc.parse_revision or 0,
                    start_index=start,
                    end_index=min(total_chunks, start + batch_chunks),
                ))
            db.commit()

        _dispatch_parallel_batches(db)
        return {"status": "queued", "batches": run.batch_count}
    finally:
        db.close()


@celery_app.task(name="kg_task.extract_knowledge_batch", bind=True, default_retry_delay=30)
def extract_knowledge_batch_task(self, batch_id: int):
    """Extract a bounded chunk range so failures and retries stay local."""
    db = SessionLocal()
    try:
        batch = db.query(KgExtractionBatch).filter(KgExtractionBatch.id == batch_id).first()
        if not batch or batch.status in {"success", "stale", "canceled"}:
            return {"status": "skipped"}
        run = db.query(KgExtractionRun).filter(KgExtractionRun.id == batch.run_id).first()
        doc = db.query(Document).filter(Document.id == batch.document_id).first()
        if not run or run.status == "canceled" or not doc or (doc.parse_revision or 0) != batch.parse_revision:
            batch.status = "stale"
            batch.finished_at = datetime.now()
            db.commit()
            return {"status": "stale"}

        batch.status = "running"
        batch.started_at = batch.started_at or datetime.now()
        db.commit()
        subject = db.query(Subject).filter(Subject.id == doc.subject_id).first()
        subject_name = subject.name if subject else "未知"
        chunks = db.query(DocumentChunk).filter(
            DocumentChunk.document_id == doc.id
        ).order_by(DocumentChunk.chunk_index).all()
        all_kps, all_rels = [], []
        for index in range(batch.start_index, min(batch.end_index, len(chunks))):
            if (doc.parse_revision or 0) != batch.parse_revision:
                batch.status = "stale"
                batch.finished_at = datetime.now()
                db.commit()
                return {"status": "stale"}
            extraction_text = _build_extraction_text(doc.title, chunks, index)
            local_data = extract_local_knowledge(extraction_text, doc.doc_type)
            try:
                data = _parse_json_response(_call_extract_entities(
                    extraction_text, subject_name, doc.doc_type
                ))
            except Exception:
                data = None
            data = _merge_extraction_payloads(data, local_data)
            if not data:
                continue
            for kp in data.get("knowledge_points", []):
                kp["_batch"] = f"{index + 1}-{index + 1}"
                kp["_chunk_id"] = chunks[index].id
            for rel in data.get("relations", []):
                rel["_chunk_id"] = chunks[index].id
            if doc.doc_type != "exam":
                data["relations"] = [rel for rel in data.get("relations", []) if rel.get("type") != "EXAMINED_IN"]
            all_kps.extend(data.get("knowledge_points", []))
            all_rels.extend(data.get("relations", []))

        doc = db.query(Document).filter(Document.id == batch.document_id).first()
        if not doc or (doc.parse_revision or 0) != batch.parse_revision:
            batch.status = "stale"
        else:
            batch.status = "success"
            batch.result_json = {"knowledge_points": all_kps, "relations": all_rels}
            batch.entity_count = len(all_kps)
            batch.relation_count = len(all_rels)
        batch.finished_at = datetime.now()
        db.commit()
        _refresh_parallel_run(db, batch.run_id)
        _dispatch_parallel_batches(db)
        return {"status": batch.status, "entities": len(all_kps), "relations": len(all_rels)}
    except Exception as exc:
        db.rollback()
        batch = db.query(KgExtractionBatch).filter(KgExtractionBatch.id == batch_id).first()
        if not batch:
            return {"status": "failed", "reason": str(exc)}
        from app.common.kg_settings import get_kg_settings
        retry_limit = get_kg_settings(db)["kg.batch_retry_limit"]
        batch.retry_count += 1
        batch.error_msg = str(exc)[:1000]
        batch.status = "dispatched" if batch.retry_count <= retry_limit else "failed"
        db.commit()
        if batch.status == "dispatched":
            raise self.retry(exc=exc)
        _refresh_parallel_run(db, batch.run_id)
        _dispatch_parallel_batches(db)
        return {"status": "failed", "reason": str(exc)}
    finally:
        db.close()


@celery_app.task(name="kg_task.finalize_document_extraction")
def finalize_document_extraction_task(run_id: int):
    """Merge successful batch payloads once and write the resulting graph."""
    db = SessionLocal()
    try:
        run = db.query(KgExtractionRun).filter(KgExtractionRun.id == run_id).first()
        if not run or run.status in {"success", "failed", "canceled"}:
            return {"status": "skipped"}
        doc = db.query(Document).filter(Document.id == run.document_id).first()
        batches = db.query(KgExtractionBatch).filter(KgExtractionBatch.run_id == run_id).all()
        if any(batch.status == "failed" for batch in batches):
            run.status = "failed"
            run.error_msg = "one or more extraction batches failed"
            run.finished_at = datetime.now()
            db.commit()
            _update_rebuild_status(db, run.rebuild_id)
            return {"status": "failed"}
        if any(batch.status != "success" for batch in batches):
            return {"status": "waiting"}

        subject = db.query(Subject).filter(Subject.id == doc.subject_id).first()
        subject_name = subject.name if subject else "未知"
        all_kps, all_rels = [], []
        for batch in batches:
            payload = batch.result_json or {}
            all_kps.extend(payload.get("knowledge_points", []))
            all_rels.extend(payload.get("relations", []))
        merged_kps, merged_rels = _merge_entities(all_kps, all_rels, doc.title, subject_name)
        if len(merged_kps) >= 2:
            merged_rels.extend(_infer_global_relationships(merged_kps, doc.title, subject_name))
            merged_rels = _dedup_relations(merged_rels)
        from app.common.kg_settings import get_kg_settings
        kg_settings = get_kg_settings(db)
        name_to_id = _store_knowledge_points(db, merged_kps, doc.subject_id, doc.id)
        rel_count = _store_relations(db, merged_rels, name_to_id, doc.id, kg_settings)
        rel_count += _link_to_existing_graph(db, merged_kps, name_to_id, doc.subject_id, doc.id, kg_settings)
        _finish_run(db, run, {
            "knowledge_points_created": len(name_to_id),
            "relations_created": rel_count,
        })
        return {"status": "success", "entities": len(name_to_id), "relations": rel_count}
    finally:
        db.close()


def _refresh_parallel_run(db, run_id: int):
    run = db.query(KgExtractionRun).filter(KgExtractionRun.id == run_id).first()
    if not run or run.status == "canceled":
        return
    batches = db.query(KgExtractionBatch).filter(KgExtractionBatch.run_id == run_id).all()
    run.processed_batches = sum(batch.status in {"success", "failed", "stale"} for batch in batches)
    db.commit()
    if batches and all(batch.status in {"success", "failed", "stale", "canceled"} for batch in batches):
        finalize_document_extraction_task.delay(run_id)


def _dispatch_parallel_batches(db):
    """Keep only the configured number of graph extraction batches in flight."""
    from app.common.kg_settings import get_kg_settings
    kg_settings = get_kg_settings(db)
    limit = kg_settings["kg.max_parallel_batches"]
    per_document_limit = kg_settings["kg.max_active_batches_per_document"]
    _release_stale_inflight_batches(db)
    active = db.query(KgExtractionBatch).filter(
        KgExtractionBatch.status.in_(("dispatched", "running")),
    ).count()
    slots = max(0, limit - active)
    if not slots:
        return
    queued = db.query(KgExtractionBatch).join(
        KgExtractionRun, KgExtractionRun.id == KgExtractionBatch.run_id,
    ).filter(
        KgExtractionBatch.status == "queued",
        KgExtractionRun.status == "running",
    ).order_by(KgExtractionRun.started_at.desc(), KgExtractionBatch.id).all()
    active_rows = db.query(KgExtractionBatch.document_id).filter(
        KgExtractionBatch.status.in_(("dispatched", "running")),
    ).all()
    active_by_document = {}
    for row in active_rows:
        active_by_document[row.document_id] = active_by_document.get(row.document_id, 0) + 1

    batches = []
    for batch in queued:
        active_for_doc = active_by_document.get(batch.document_id, 0)
        if active_for_doc >= per_document_limit:
            continue
        batches.append(batch)
        active_by_document[batch.document_id] = active_for_doc + 1
        if len(batches) >= slots:
            break
    for batch in batches:
        batch.status = "dispatched"
    db.commit()
    for batch in batches:
        extract_knowledge_batch_task.delay(batch.id)


def _release_stale_inflight_batches(db, timeout_minutes: int = 30):
    """Return batches abandoned by worker restarts to the queue."""
    cutoff = datetime.now() - timedelta(minutes=timeout_minutes)
    db.query(KgExtractionBatch).filter(
        KgExtractionBatch.status == "dispatched",
        KgExtractionBatch.started_at.is_(None),
        KgExtractionBatch.created_at < cutoff,
    ).update({"status": "queued"}, synchronize_session=False)
    db.query(KgExtractionBatch).filter(
        KgExtractionBatch.status == "running",
        KgExtractionBatch.started_at.isnot(None),
        KgExtractionBatch.started_at < cutoff,
    ).update({"status": "queued", "started_at": None}, synchronize_session=False)
    db.commit()


@celery_app.task(name="kg_task.extract_knowledge", bind=True, max_retries=2, default_retry_delay=60)
def extract_knowledge_task(self, document_id: int, run_id: int = None):
    db = SessionLocal()
    run = None
    try:
        if not run_id:
            from app.common.schema_migrations import KG_REBUILD_VERSION
            run = KgExtractionRun(document_id=document_id, version=KG_REBUILD_VERSION, status="queued")
            db.add(run)
            db.commit()
            db.refresh(run)
            run_id = run.id
        if run_id:
            run = db.query(KgExtractionRun).filter(KgExtractionRun.id == run_id).first()
            if run:
                run.status = "running"
                run.model = settings.llm_model
                run.started_at = datetime.now()
                db.commit()
        doc = db.query(Document).filter(Document.id == document_id).first()
        if not doc or doc.parse_status != "success":
            if run:
                run.status = "failed"
                run.error_msg = "document not parsed successfully"
                run.finished_at = datetime.now()
                db.commit()
                _update_rebuild_status(db, run.rebuild_id)
            return {"status": "skipped", "reason": "document not parsed successfully"}

        subject = db.query(Subject).filter(Subject.id == doc.subject_id).first()
        subject_name = subject.name if subject else "未知"
        from app.common.kg_settings import get_kg_settings
        kg_settings = get_kg_settings(db)

        chunks = (
            db.query(DocumentChunk)
            .filter(DocumentChunk.document_id == document_id)
            .order_by(DocumentChunk.chunk_index)
            .all()
        )
        if not chunks:
            if run:
                run.status = "failed"
                run.error_msg = "no chunks"
                run.finished_at = datetime.now()
                db.commit()
                _update_rebuild_status(db, run.rebuild_id)
            return {"status": "skipped", "reason": "no chunks"}

        total_chunks = len(chunks)
        if run:
            run.batch_count = (total_chunks + BATCH_SIZE - 1) // BATCH_SIZE
            db.commit()

        # ── Phase 1: Batch extract entities from chunks ──
        all_kps = []
        all_rels = []

        for batch_start in range(0, total_chunks, BATCH_SIZE):
            batch = chunks[batch_start:batch_start + BATCH_SIZE]
            batch_text = _build_extraction_text(doc.title, chunks, batch_start)
            try:
                response = _call_extract_entities(batch_text, subject_name, doc.doc_type)
                data = _parse_json_response(response)
                data = _merge_extraction_payloads(data, extract_local_knowledge(batch_text, doc.doc_type))
                if data:
                    for kp in data.get("knowledge_points", []):
                        kp["_batch"] = f"{batch_start + 1}-{batch_start + len(batch)}"
                        kp["_chunk_id"] = batch[0].id if batch else None
                    for rel in data.get("relations", []):
                        rel["_chunk_id"] = batch[0].id if batch else None
                    if doc.doc_type != "exam":
                        data["relations"] = [rel for rel in data.get("relations", []) if rel.get("type") != "EXAMINED_IN"]
                    all_kps.extend(data.get("knowledge_points", []))
                    all_rels.extend(data.get("relations", []))
            except Exception:
                # A malformed or transient batch must not discard the rest of a large document.
                data = extract_local_knowledge(batch_text, doc.doc_type)
                for kp in data.get("knowledge_points", []):
                    kp["_batch"] = f"{batch_start + 1}-{batch_start + len(batch)}"
                    kp["_chunk_id"] = batch[0].id if batch else None
                for rel in data.get("relations", []):
                    rel["_chunk_id"] = batch[0].id if batch else None
                all_kps.extend(data.get("knowledge_points", []))
                all_rels.extend(data.get("relations", []))
            if run:
                run.processed_batches = min(run.batch_count, run.processed_batches + 1)
                db.commit()

        if not all_kps:
            result = {"status": "completed", "knowledge_points_created": 0, "relations_created": 0, "reason": "no entities extracted"}
            _finish_run(db, run, result)
            return result

        # ── Phase 2: Merge & deduplicate entities across batches ──
        merged_kps, merged_rels = _merge_entities(all_kps, all_rels, doc.title, subject_name)

        # ── Phase 2.5: Global relationship inference ──
        # Find relationships between entities extracted from different batches
        if len(merged_kps) >= 2:
            global_rels = _infer_global_relationships(merged_kps, doc.title, subject_name)
            merged_rels.extend(global_rels)
            # Deduplicate again
            merged_rels = _dedup_relations(merged_rels)

        # ── Phase 3: Store in DB and Neo4j ──
        name_to_id = _store_knowledge_points(db, merged_kps, doc.subject_id, doc.id)

        rel_count = _store_relations(db, merged_rels, name_to_id, doc.id, kg_settings)

        # ── Phase 4: Cross-document linking ──
        cross_links = _link_to_existing_graph(db, merged_kps, name_to_id, doc.subject_id, doc.id, kg_settings)
        rel_count += cross_links

        result = {
            "status": "success",
            "knowledge_points_created": len(name_to_id),
            "relations_created": rel_count,
            "cross_document_links": cross_links,
            "batches_processed": (total_chunks + BATCH_SIZE - 1) // BATCH_SIZE,
        }
        _finish_run(db, run, result)
        return result

    except Exception as e:
        db.rollback()
        if run_id:
            run = db.query(KgExtractionRun).filter(KgExtractionRun.id == run_id).first()
            if run:
                run.status = "failed"
                run.error_msg = str(e)[:1000]
                run.finished_at = datetime.now()
                db.commit()
                _update_rebuild_status(db, run.rebuild_id)
        return {"status": "failed", "reason": str(e)}
    finally:
        db.close()


def _build_extraction_text(doc_title: str, chunks: list, index: int) -> str:
    parts = [f"文档标题：{doc_title}"]
    if index > 0:
        parts.append(f"[前文，仅用于理解上下文]\n{chunks[index - 1].content[:500]}")
    parts.append(f"[主切块，实体和证据必须来自这里]\n{chunks[index].content[:MAX_CHARS_PER_CHUNK]}")
    if index + 1 < len(chunks):
        parts.append(f"[后文，仅用于理解上下文]\n{chunks[index + 1].content[:500]}")
    return "\n\n---\n\n".join(parts)


def _call_extract_entities(batch_text: str, subject_name: str, doc_type: str) -> str:
    if not _has_remote_llm_config():
        raise RuntimeError("remote llm api key is not configured")
    prompt = f"""你是学科知识图谱构建专家。请从主切块中提取细粒度、可解释的实体和关系。

所属科目：{subject_name}
文档类型：{doc_type}

文档内容：
{batch_text}

要求：
1. 只从“主切块”提取实体；前文和后文仅用于消歧，不能作为证据来源。
2. 实体包括概念、术语、机制、算法、定理、关键组件和重要参数；过滤普通描述词、章节名和过于宽泛的词。
3. 实体名称应简洁准确（2-30字），优先标准名称；缩写放入 aliases。
4. 每个实体必须返回 entity_type、evidence 和 confidence。
5. 每条关系必须有明确方向、具体学科含义、主切块原文证据和 confidence。
6. 关系类型：
   - PREREQUISITE：源实体是学习或理解目标实体的必要基础。
   - NEXT：目标实体是源实体的直接后续过程或扩展。
   - CONTAINS：源实体由目标组件组成，或覆盖目标子概念。
   - CONTRAST：两个实体存在明确的对比维度。
   - RELATED：仅当原文明示关联且无法归入以上类型时使用。
7. 普通教材禁止生成 EXAMINED_IN；仅真题语境允许生成。
8. 不要因为两个实体同时出现就创建 RELATED，不要编造隐含联系。

请严格按照以下JSON格式返回，不要包含markdown代码块标记：
{{
  "knowledge_points": [
    {{"name": "知识点名称", "aliases": ["缩写或别名"], "entity_type": "概念或组件", "description": "知识点描述", "difficulty": 3, "evidence": "主切块原文依据", "confidence": 0.85}}
  ],
  "relations": [
    {{"source": "源知识点名称", "target": "目标知识点名称", "type": "CONTAINS", "description": "具体关系描述", "evidence": "主切块原文依据", "confidence": 0.85}}
  ]
}}"""

    return chat(
        messages=[
            {"role": "system", "content": "你是一个知识抽取专家，只返回纯JSON，不要包含markdown代码块标记。"},
            {"role": "user", "content": prompt},
        ],
        temperature=0.2,
        max_tokens=4096,
    )


def _has_remote_llm_config() -> bool:
    key = (settings.deepseek_api_key or "").strip()
    return bool(key and "your-deepseek-api-key" not in key and "sk-your" not in key)


def _merge_extraction_payloads(llm_data: dict, local_data: dict) -> dict:
    data = llm_data or {"knowledge_points": [], "relations": []}
    local_data = local_data or {"knowledge_points": [], "relations": []}
    data["knowledge_points"] = list(data.get("knowledge_points") or []) + list(local_data.get("knowledge_points") or [])
    data["relations"] = list(data.get("relations") or []) + list(local_data.get("relations") or [])
    return data


def _merge_entities(all_kps: list, all_rels: list, doc_title: str, subject_name: str) -> tuple:
    """Merge and deduplicate entities across batches."""
    if not all_kps:
        return [], []

    seen_names = {}
    canonical_names = {}
    unique_kps = []
    for kp in all_kps:
        name = kp.get("name", "").strip()
        if not _is_valid_extracted_entity(name):
            continue
        normalized = _normalize_entity_name(name)
        aliases = [alias.strip() for alias in kp.get("aliases", []) if isinstance(alias, str) and alias.strip()]
        matched = seen_names.get(normalized)
        if not matched:
            matched = next((seen_names.get(_normalize_entity_name(alias)) for alias in aliases if seen_names.get(_normalize_entity_name(alias))), None)
        if not matched:
            kp["name"] = name
            seen_names[normalized] = kp
            for alias in aliases:
                seen_names[_normalize_entity_name(alias)] = kp
            canonical_names[name] = name
            unique_kps.append(kp)
        else:
            existing = matched
            canonical_names[name] = existing["name"]
            if len(kp.get("description", "")) > len(existing.get("description", "")):
                existing["description"] = kp["description"]
            if kp.get("difficulty") and not existing.get("difficulty"):
                existing["difficulty"] = kp["difficulty"]
            existing["aliases"] = sorted(set(existing.get("aliases", []) + kp.get("aliases", []) + [name]))
            for alias in existing["aliases"]:
                seen_names[_normalize_entity_name(alias)] = existing

    for rel in all_rels:
        rel["source"] = canonical_names.get(rel.get("source", "").strip(), rel.get("source", "").strip())
        rel["target"] = canonical_names.get(rel.get("target", "").strip(), rel.get("target", "").strip())

    unique_rels = _dedup_relations(all_rels)
    return unique_kps, unique_rels


def _normalize_entity_name(name: str) -> str:
    text = unicodedata.normalize("NFKC", name or "").strip().lower()
    text = re.sub(r"[\s·_\-]+", "", text)
    return re.sub(r"[()（）\[\]【】]", "", text)


def _is_valid_extracted_entity(name: str) -> bool:
    name = (name or "").strip()
    if not name or len(name) < 2 or len(name) > 100:
        return False
    if re.fullmatch(r"\d+(?:\.\d+)*", name):
        return False
    if re.fullmatch(r"[a-z_][a-z0-9_]{2,}", name):
        allowed = {
            "transformer", "bert", "gpt", "cnn", "rnn", "lstm", "gru", "relu",
            "softmax", "dropout", "adam", "sgd", "resnet", "vgg", "gan", "svm",
        }
        return name.lower() in allowed
    if re.fullmatch(r"[a-z][a-z0-9_]*s", name):
        return False
    return bool(re.search(r"[\u4e00-\u9fffA-Za-z]", name))


def _dedup_relations(rels: list) -> list:
    """Deduplicate relations by (source, target, type)."""
    seen = set()
    unique = []
    for rel in rels:
        source = rel.get("source", "").strip()
        target = rel.get("target", "").strip()
        rel_type = rel.get("type", "RELATED").strip().upper()
        if not source or not target or source == target or rel_type not in VALID_RELATION_TYPES:
            continue
        rel["source"] = source
        rel["target"] = target
        rel["type"] = rel_type
        key = (source, target, rel_type)
        if key not in seen:
            seen.add(key)
            unique.append(rel)
    return unique


def _infer_global_relationships(kps: list, doc_title: str, subject_name: str) -> list:
    """
    Use LLM to infer relationships between ALL extracted entities.
    This catches cross-batch connections that were missed in Phase 1.
    """
    if len(kps) < 2 or not _has_remote_llm_config():
        return []

    relationships = []
    step = max(1, GLOBAL_REL_WINDOW_SIZE - GLOBAL_REL_WINDOW_OVERLAP)
    for start in range(0, len(kps), step):
        selected_kps = kps[start:start + GLOBAL_REL_WINDOW_SIZE]
        if len(selected_kps) < 2:
            continue
        relationships.extend(_infer_global_relationship_window(selected_kps, doc_title, subject_name))
    return _dedup_relations(relationships)


def _infer_global_relationship_window(selected_kps: list, doc_title: str, subject_name: str) -> list:
    """Infer cross-chunk relationships for one bounded entity window."""

    kp_text = "\n".join(
        f"{i+1}. {kp['name']}：{kp.get('description', '')}"
        for i, kp in enumerate(selected_kps)
    )

    prompt = f"""你是一个知识体系构建专家。以下是同一篇文档中提取出的所有知识点，它们来自文档的不同章节，请找出它们之间可能存在的关联关系。

文档标题：{doc_title}
所属科目：{subject_name}

知识点列表：
{kp_text}

请分析以上知识点之间的逻辑关系。注意：知识点来自文档的不同部分，有些关联可能是隐含的、跨章节的。
要求：
1. 仔细分析每对知识点之间的可能关系
2. 关系类型：PREREQUISITE（必要基础）、NEXT（直接后续）、RELATED（原文明示关联）、CONTAINS（组成或包含）、CONTRAST（明确对比）
3. 只保留有明确语义依据的关系；没有可靠联系时不要为了数量强行添加
4. 只返回确实存在的关系，不要编造不存在的关联
5. 关系描述应简洁说明两个知识点之间的具体联系（10-40字）
6. 每条关系必须返回 evidence 和 confidence；无法给出具体依据时不要输出

请严格按照以下JSON格式返回：
{{
  "relations": [
    {{"source": "知识点A名称", "target": "知识点B名称", "type": "PREREQUISITE", "description": "A是学习B的基础", "evidence": "语义依据", "confidence": 0.85}}
  ]
}}"""

    response = chat(
        messages=[
            {"role": "system", "content": "你是一个知识体系构建专家，只返回纯JSON，不要包含markdown代码块标记。"},
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,
        max_tokens=4096,
    )

    data = _parse_json_response(response)
    if data:
        return data.get("relations", [])
    return []


def _llm_merge_entities(kps: list, rels: list, doc_title: str, subject_name: str) -> tuple:
    """Use LLM to merge and consolidate entities when there are many."""
    kp_text = "\n".join(
        f"- {kp['name']}：{kp.get('description', '')}（难度{kp.get('difficulty', 3)}）"
        for kp in kps
    )
    rel_text = "\n".join(
        f"- {r['source']} → {r['target']}（{r.get('type', 'RELATED')}）"
        for r in rels
    )

    prompt = f"""你是一个知识体系整理专家。请对以下从文档中提取的知识点和关系进行合并去重。

文档标题：{doc_title}
所属科目：{subject_name}

当前知识点（共{len(kps)}个）：
{kp_text}

当前关系（共{len(rels)}个）：
{rel_text}

要求：
1. 合并名称不同但指向同一概念的知识点（如"CNN"和"卷积神经网络"应该合并）
2. 保留更规范、更标准的名称作为合并后的名称
3. 合并后知识点不超过30个
4. 更新关系中的知识点名称以匹配合并后的名称
5. 删除重复或无意义的关系

请按照以下JSON格式返回合并后的结果：
{{
  "knowledge_points": [
    {{"name": "规范名称", "description": "合并后的描述", "difficulty": 3}}
  ],
  "relations": [
    {{"source": "源知识点", "target": "目标知识点", "type": "RELATED", "description": "关系描述"}}
  ]
}}"""

    response = chat(
        messages=[
            {"role": "system", "content": "你是一个知识体系整理专家，只返回纯JSON。"},
            {"role": "user", "content": prompt},
        ],
        temperature=0.2,
        max_tokens=4096,
    )

    data = _parse_json_response(response)
    if data:
        return data.get("knowledge_points", kps), data.get("relations", rels)
    return kps, rels


def _store_knowledge_points(db, kps: list, subject_id: int, document_id: int = None) -> dict:
    """Store knowledge points in MySQL and Neo4j. Returns name→id mapping."""
    name_to_id = {}
    existing_by_normalized_name = {
        _normalize_entity_name(point.name): point
        for point in db.query(KnowledgePoint).filter(KnowledgePoint.subject_id == subject_id).all()
    }

    for kp in kps:
        name = kp.get("name", "").strip()
        if not name:
            continue

        normalized_name = _normalize_entity_name(name)
        existing = existing_by_normalized_name.get(normalized_name)

        if existing:
            name_to_id[name] = existing.id
            if kp.get("description") and not existing.description:
                existing.description = kp.get("description")
                db.commit()
            try:
                neo4j_create_node(existing.id, existing.name, existing.subject_id)
            except Exception as exc:
                _record_sync_failure(db, "upsert", "node", existing.id, {"name": existing.name}, exc)
            _store_source(db, existing.id, document_id, kp, existing.name)
            continue

        point = KnowledgePoint(
            name=name,
            subject_id=subject_id,
            description=kp.get("description", ""),
            difficulty=kp.get("difficulty", 3),
            origin="auto",
            confidence=_safe_confidence(kp.get("confidence")),
            review_status="pending",
        )
        db.add(point)
        db.commit()
        db.refresh(point)

        try:
            neo4j_create_node(point.id, point.name, point.subject_id)
        except Exception as exc:
            _record_sync_failure(db, "upsert", "node", point.id, {"name": point.name}, exc)

        name_to_id[name] = point.id
        existing_by_normalized_name[normalized_name] = point
        _store_source(db, point.id, document_id, kp, point.name)

    return name_to_id


def _store_relations(db, rels: list, name_to_id: dict, document_id: int, kg_settings: dict) -> int:
    """Store relations in MySQL and Neo4j."""
    count = 0
    for rel in rels:
        src_name = rel.get("source", "").strip()
        tgt_name = rel.get("target", "").strip()
        src_id = name_to_id.get(src_name)
        tgt_id = name_to_id.get(tgt_name)
        if not src_id or not tgt_id or src_id == tgt_id:
            continue

        rel_type = rel.get("type", "RELATED").strip().upper()
        if rel_type not in VALID_RELATION_TYPES:
            continue
        rel_desc = rel.get("description", "")
        confidence = _safe_confidence(rel.get("confidence"))
        if confidence < kg_settings["kg.relation_candidate_threshold"]:
            continue
        if confidence < kg_settings["kg.relation_auto_threshold"]:
            _store_relation_candidate(db, src_id, tgt_id, rel, document_id)
            continue

        existing_rel = (
            db.query(KnowledgeRelation)
            .filter(
                KnowledgeRelation.source_node_id == src_id,
                KnowledgeRelation.target_node_id == tgt_id,
                KnowledgeRelation.relation_type == rel_type,
            )
            .first()
        )
        if existing_rel:
            _store_relation_evidence(db, existing_rel.id, document_id, rel)
            try:
                neo4j_create_relation(src_id, tgt_id, rel_type, rel_desc)
            except Exception as exc:
                _record_sync_failure(db, "upsert", "relation", existing_rel.id, rel, exc)
            continue

        relation = KnowledgeRelation(
            source_node_id=src_id,
            target_node_id=tgt_id,
            relation_type=rel_type,
            description=rel_desc,
            origin="auto",
            confidence=confidence,
            review_status="pending",
        )
        db.add(relation)
        db.commit()
        _store_relation_evidence(db, relation.id, document_id, rel)
        try:
            neo4j_create_relation(src_id, tgt_id, rel_type, rel_desc)
        except Exception as exc:
            _record_sync_failure(db, "upsert", "relation", relation.id, rel, exc)
        count += 1

    return count


def _link_to_existing_graph(db, new_kps: list, name_to_id: dict, subject_id: int, document_id: int, kg_settings: dict) -> int:
    """
    Link newly extracted entities to existing knowledge graph nodes
    in the same subject using LLM-based relationship discovery.
    """
    if len(new_kps) < 1 or not _has_remote_llm_config():
        return 0

    # Get existing entities in the same subject (excluding the ones just created)
    new_ids = set(name_to_id.values())
    active_source = exists().where(and_(
        KnowledgePointSource.knowledge_point_id == KnowledgePoint.id,
        KnowledgePointSource.document_id == Document.id,
    ))
    existing_kps = (
        db.query(KnowledgePoint)
        .filter(
            KnowledgePoint.subject_id == subject_id,
            ~KnowledgePoint.id.in_(new_ids),
            or_(KnowledgePoint.origin == "manual", active_source),
        )
        .limit(kg_settings["kg.cross_relation_top_k"])
        .all()
    )

    if not existing_kps:
        return 0

    for point in existing_kps:
        try:
            neo4j_create_node(point.id, point.name, point.subject_id)
        except Exception as exc:
            _record_sync_failure(db, "upsert", "node", point.id, {"name": point.name}, exc)

    # Select a sample of new entities to link (top by difficulty)
    sorted_new = sorted(new_kps, key=lambda k: k.get("difficulty", 3), reverse=True)
    sample_new = sorted_new[:20]

    new_text = "\n".join(
        f"- {kp['name']}：{kp.get('description', '')}"
        for kp in sample_new
    )
    existing_text = "\n".join(
        f"- {kp.name}：{kp.description or ''}"
        for kp in existing_kps
    )

    prompt = f"""你是一个知识图谱构建专家。请找出新提取的知识点和已有知识点之间的关联关系。

新知识点：
{new_text}

已有知识点：
{existing_text}

要求：
1. 只找出确实存在语义关联的知识点对
2. 关系类型：PREREQUISITE（必要基础）、NEXT（直接后续）、RELATED（原文明示关联）、CONTAINS（组成或包含）、CONTRAST（明确对比）
3. 关系描述应简洁说明具体联系（10-30字）
4. 知识点名称必须和上面列出的完全一致（一字不差）
5. 每条关系必须返回 evidence 和 confidence；无法说明具体学科含义时不要输出

请按JSON格式返回：
{{
  "relations": [
    {{"source": "已有知识点名称（必须是已有列表中的）", "target": "新知识点名称（必须是新列表中的）", "type": "RELATED", "description": "关系描述", "evidence": "语义依据", "confidence": 0.85}}
  ]
}}"""

    response = chat(
        messages=[
            {"role": "system", "content": "你是一个知识图谱构建专家，只返回纯JSON。"},
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,
        max_tokens=4096,
    )

    data = _parse_json_response(response)
    if not data:
        return 0

    relations = data.get("relations", [])
    # Build lookup: existing entity name → id
    existing_name_to_id = {kp.name: kp.id for kp in existing_kps}

    count = 0
    for rel in relations:
        src_name = rel.get("source", "").strip()
        tgt_name = rel.get("target", "").strip()
        src_id = existing_name_to_id.get(src_name)
        tgt_id = name_to_id.get(tgt_name)

        if not src_id or not tgt_id or src_id == tgt_id:
            # Try reversed: source might be new, target might be existing
            src_id = name_to_id.get(src_name)
            tgt_id = existing_name_to_id.get(tgt_name)

        if not src_id or not tgt_id or src_id == tgt_id:
            continue

        rel_type = rel.get("type", "RELATED").strip().upper()
        if rel_type not in VALID_RELATION_TYPES:
            continue
        rel_desc = rel.get("description", "")
        confidence = _safe_confidence(rel.get("confidence"))
        if confidence < kg_settings["kg.relation_candidate_threshold"]:
            continue
        if confidence < kg_settings["kg.relation_auto_threshold"]:
            _store_relation_candidate(db, src_id, tgt_id, rel, document_id)
            continue

        existing_rel = (
            db.query(KnowledgeRelation)
            .filter(
                KnowledgeRelation.source_node_id == src_id,
                KnowledgeRelation.target_node_id == tgt_id,
                KnowledgeRelation.relation_type == rel_type,
            )
            .first()
        )
        if existing_rel:
            _store_relation_evidence(db, existing_rel.id, document_id, rel)
            try:
                neo4j_create_relation(src_id, tgt_id, rel_type, rel_desc)
            except Exception as exc:
                _record_sync_failure(db, "upsert", "relation", existing_rel.id, rel, exc)
            continue

        relation = KnowledgeRelation(
            source_node_id=src_id,
            target_node_id=tgt_id,
            relation_type=rel_type,
            description=rel_desc,
            origin="auto",
            confidence=confidence,
            review_status="pending",
        )
        db.add(relation)
        db.commit()
        _store_relation_evidence(db, relation.id, document_id, rel)
        try:
            neo4j_create_relation(src_id, tgt_id, rel_type, rel_desc)
        except Exception as exc:
            _record_sync_failure(db, "upsert", "relation", relation.id, rel, exc)
        count += 1

    return count


def _parse_json_response(text: str) -> dict:
    text = text.strip()
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        text = match.group()
    try:
        data = json.loads(text)
        if not isinstance(data, dict):
            return None
        if "knowledge_points" in data and not isinstance(data["knowledge_points"], list):
            return None
        if "relations" in data and not isinstance(data["relations"], list):
            return None
        return data
    except json.JSONDecodeError:
        return None


def _safe_confidence(value, default: float = 0.8) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return default


def _store_source(db, point_id: int, document_id: int, kp: dict, canonical_name: str):
    if not document_id:
        return
    existing = db.query(KnowledgePointSource).filter(
        KnowledgePointSource.knowledge_point_id == point_id,
        KnowledgePointSource.document_id == document_id,
        KnowledgePointSource.chunk_id == kp.get("_chunk_id"),
    ).first()
    if existing:
        existing.raw_name = kp.get("name", canonical_name)[:100]
        existing.canonical_name = canonical_name[:100]
        existing.evidence_text = (kp.get("evidence") or kp.get("description") or "")[:1000]
        existing.extraction_batch = kp.get("_batch")
        existing.confidence = max(float(existing.confidence), _safe_confidence(kp.get("confidence")))
        db.commit()
        return
    source = KnowledgePointSource(
        knowledge_point_id=point_id,
        document_id=document_id,
        chunk_id=kp.get("_chunk_id"),
        raw_name=kp.get("name", canonical_name)[:100],
        canonical_name=canonical_name[:100],
        evidence_text=(kp.get("evidence") or kp.get("description") or "")[:1000],
        extraction_batch=kp.get("_batch"),
        confidence=_safe_confidence(kp.get("confidence")),
    )
    db.add(source)
    db.commit()


def _store_relation_evidence(db, relation_id: int, document_id: int, rel: dict):
    existing = db.query(KnowledgeRelationEvidence).filter(
        KnowledgeRelationEvidence.relation_id == relation_id,
        KnowledgeRelationEvidence.document_id == document_id,
        KnowledgeRelationEvidence.chunk_id == rel.get("_chunk_id"),
        KnowledgeRelationEvidence.source_name == rel.get("source", "")[:100],
        KnowledgeRelationEvidence.target_name == rel.get("target", "")[:100],
        KnowledgeRelationEvidence.relation_type == rel.get("type", "RELATED")[:30],
    ).first()
    if existing:
        existing.evidence_text = (rel.get("evidence") or rel.get("description") or "")[:1000]
        existing.confidence = max(float(existing.confidence), _safe_confidence(rel.get("confidence")))
        existing.prompt_version = PROMPT_VERSION
        db.commit()
        return
    db.add(KnowledgeRelationEvidence(
        relation_id=relation_id,
        document_id=document_id,
        chunk_id=rel.get("_chunk_id"),
        source_name=rel.get("source", "")[:100],
        target_name=rel.get("target", "")[:100],
        relation_type=rel.get("type", "RELATED")[:30],
        evidence_text=(rel.get("evidence") or rel.get("description") or "")[:1000],
        confidence=_safe_confidence(rel.get("confidence")),
        prompt_version=PROMPT_VERSION,
    ))
    db.commit()


def _store_relation_candidate(db, source_id: int, target_id: int, rel: dict, document_id: int):
    rel_type = rel.get("type", "RELATED").strip().upper()
    existing = db.query(KnowledgeRelationCandidate).filter(
        KnowledgeRelationCandidate.source_node_id == source_id,
        KnowledgeRelationCandidate.target_node_id == target_id,
        KnowledgeRelationCandidate.relation_type == rel_type,
        KnowledgeRelationCandidate.status == "pending",
    ).first()
    if existing:
        if _safe_confidence(rel.get("confidence")) > float(existing.confidence):
            existing.description = rel.get("description", "")
            existing.evidence_text = rel.get("evidence", "")
            existing.confidence = _safe_confidence(rel.get("confidence"))
        db.commit()
        return
    db.add(KnowledgeRelationCandidate(
        source_node_id=source_id,
        target_node_id=target_id,
        relation_type=rel_type,
        description=rel.get("description", ""),
        evidence_text=rel.get("evidence", ""),
        confidence=_safe_confidence(rel.get("confidence")),
        document_id=document_id,
        chunk_id=rel.get("_chunk_id"),
        prompt_version=PROMPT_VERSION,
    ))
    db.commit()


def _record_sync_failure(db, operation: str, entity_type: str, entity_id: int, payload: dict, error: Exception):
    db.add(KgSyncFailure(
        operation=operation,
        entity_type=entity_type,
        entity_id=entity_id,
        payload=payload,
        error_msg=str(error)[:1000],
    ))
    db.commit()


def _finish_run(db, run: KgExtractionRun, result: dict):
    if not run:
        return
    run.status = "success"
    run.entity_count = result.get("knowledge_points_created", 0)
    run.relation_count = result.get("relations_created", 0)
    run.finished_at = datetime.now()
    db.commit()
    _update_rebuild_status(db, run.rebuild_id)
    from app.tasks.kg_rebuild import retry_neo4j_sync_task
    retry_neo4j_sync_task.delay()


def _update_rebuild_status(db, rebuild_id: int):
    if not rebuild_id:
        return
    rebuild = db.query(KgRebuild).filter(KgRebuild.id == rebuild_id).first()
    if not rebuild:
        return
    runs = db.query(KgExtractionRun).filter(KgExtractionRun.rebuild_id == rebuild_id).all()
    rebuild.completed_documents = sum(run.status == "success" for run in runs)
    rebuild.failed_documents = sum(run.status == "failed" for run in runs)
    if rebuild.completed_documents + rebuild.failed_documents >= rebuild.total_documents:
        rebuild.status = "partial_failed" if rebuild.failed_documents else "success"
        rebuild.finished_at = datetime.now()
    db.commit()
    if rebuild.status in {"success", "partial_failed", "failed"}:
        from app.common.schema_migrations import enqueue_auto_rebuild
        enqueue_auto_rebuild()
