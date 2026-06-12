from datetime import datetime

from sqlalchemy import inspect, text
from sqlalchemy.exc import OperationalError

from app.database import engine


KG_REBUILD_VERSION = "kg-v5-all-entities-search-edit"
PREVIOUS_KG_REBUILD_VERSION = "kg-v4-parallel-extraction"


def ensure_kg_schema():
    """Apply small idempotent schema additions for existing Docker volumes."""
    inspector = inspect(engine)
    column_info = {
        table: {column["name"]: column for column in inspector.get_columns(table)}
        for table in ("documents", "knowledge_points", "knowledge_relations", "kg_extraction_runs", "kg_extraction_batches")
        if inspector.has_table(table)
    }
    columns = {
        table: set(table_columns)
        for table, table_columns in column_info.items()
    }
    additions = {
        "documents": {
            "parse_revision": "INT NOT NULL DEFAULT 0",
        },
        "knowledge_points": {
            "origin": "ENUM('legacy','manual','auto') NOT NULL DEFAULT 'legacy'",
            "confidence": "DECIMAL(4,3) NOT NULL DEFAULT 1.000",
            "review_status": "ENUM('pending','approved','rejected') NOT NULL DEFAULT 'pending'",
        },
        "knowledge_relations": {
            "origin": "ENUM('legacy','manual','auto') NOT NULL DEFAULT 'legacy'",
            "confidence": "DECIMAL(4,3) NOT NULL DEFAULT 1.000",
            "review_status": "ENUM('pending','approved','rejected') NOT NULL DEFAULT 'pending'",
        },
        "kg_extraction_runs": {
            "status": "ENUM('queued','running','success','failed','canceled') NOT NULL DEFAULT 'queued'",
        },
    }
    with engine.begin() as connection:
        for table, table_additions in additions.items():
            for column, definition in table_additions.items():
                if column not in columns.get(table, set()):
                    connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {definition}"))
        connection.execute(text("SET SESSION lock_wait_timeout = 3"))
        try:
            run_status_type = str(column_info.get("kg_extraction_runs", {}).get("status", {}).get("type", ""))
            if inspector.has_table("kg_extraction_runs") and "canceled" not in run_status_type:
                connection.execute(text("""
                    ALTER TABLE kg_extraction_runs
                    MODIFY COLUMN status ENUM('queued','running','success','failed','canceled')
                    NOT NULL DEFAULT 'queued'
                """))
            batch_status_type = str(column_info.get("kg_extraction_batches", {}).get("status", {}).get("type", ""))
            if inspector.has_table("kg_extraction_batches") and "dispatched" not in batch_status_type:
                connection.execute(text("""
                    ALTER TABLE kg_extraction_batches
                    MODIFY COLUMN status ENUM('queued','dispatched','running','success','failed','stale','canceled')
                    NOT NULL DEFAULT 'queued'
                """))
        except OperationalError:
            # Do not block application startup behind long-running extraction queries.
            pass
        defaults = {
            "chunk.min_chars": ("120", "文档最小切块大小"),
            "chunk.size": ("512", "文档目标切块大小"),
            "chunk.overlap": ("128", "文档切块重叠量"),
            "kg.relation_candidate_threshold": ("0.2", "关系候选保留阈值"),
            "kg.relation_auto_threshold": ("0.8", "关系自动入图阈值"),
            "kg.batch_chunks": ("20", "每个并行抽取分段包含的切块数"),
            "kg.max_parallel_batches": ("8", "图谱抽取最大并行分段数"),
            "kg.batch_retry_limit": ("2", "图谱抽取分段失败重试次数"),
            "kg.cross_relation_top_k": ("30", "跨文档关系候选召回数量"),
        }
        for key, (value, description) in defaults.items():
            connection.execute(text("""
                INSERT IGNORE INTO system_configs (config_key, config_value, description)
                VALUES (:key, :value, :description)
            """), {"key": key, "value": value, "description": description})
    reconcile_kg_document_references()


def reconcile_kg_document_references():
    """Remove historical KG rows that reference documents no longer in the knowledge base."""
    try:
        with engine.begin() as connection:
            connection.execute(text("""
                DELETE c FROM knowledge_relation_candidates c
                LEFT JOIN documents d ON d.id = c.document_id
                WHERE c.document_id IS NOT NULL AND d.id IS NULL
            """))
            connection.execute(text("""
                DELETE e FROM knowledge_relation_evidence e
                LEFT JOIN documents d ON d.id = e.document_id
                WHERE d.id IS NULL
            """))
            connection.execute(text("""
                DELETE s FROM knowledge_point_sources s
                LEFT JOIN documents d ON d.id = s.document_id
                WHERE d.id IS NULL
            """))
            connection.execute(text("""
                UPDATE kg_extraction_runs r
                LEFT JOIN documents d ON d.id = r.document_id
                SET r.status = 'canceled', r.error_msg = '关联文档已删除'
                WHERE d.id IS NULL AND r.status IN ('queued', 'running')
            """))
            connection.execute(text("""
                UPDATE kg_extraction_batches b
                LEFT JOIN documents d ON d.id = b.document_id
                SET b.status = 'stale', b.error_msg = '关联文档已删除'
                WHERE d.id IS NULL AND b.status IN ('queued', 'dispatched', 'running')
            """))
            connection.execute(text("""
                DELETE r FROM knowledge_relations r
                WHERE r.origin = 'auto'
                  AND NOT EXISTS (
                    SELECT 1
                    FROM knowledge_relation_evidence e
                    JOIN documents d ON d.id = e.document_id
                    WHERE e.relation_id = r.id
                  )
            """))
            connection.execute(text("""
                DELETE r FROM knowledge_relations r
                JOIN knowledge_points p
                  ON p.id = r.source_node_id OR p.id = r.target_node_id
                WHERE p.origin = 'auto'
                  AND NOT EXISTS (
                    SELECT 1
                    FROM knowledge_point_sources s
                    JOIN documents d ON d.id = s.document_id
                    WHERE s.knowledge_point_id = p.id
                  )
            """))
            connection.execute(text("""
                DELETE c FROM knowledge_relation_candidates c
                LEFT JOIN knowledge_points s ON s.id = c.source_node_id
                LEFT JOIN knowledge_points t ON t.id = c.target_node_id
                WHERE s.id IS NULL OR t.id IS NULL
            """))
            connection.execute(text("""
                DELETE p FROM knowledge_points p
                WHERE p.origin = 'auto'
                  AND NOT EXISTS (
                    SELECT 1
                    FROM knowledge_point_sources s
                    JOIN documents d ON d.id = s.document_id
                    WHERE s.knowledge_point_id = p.id
                  )
            """))
    except OperationalError:
        # Startup should not fail because a legacy volume is temporarily locked by workers.
        pass


def enqueue_auto_rebuild():
    """Create one rebuild record per schema version and enqueue it exactly once."""
    from app.database import SessionLocal
    from app.models import KgRebuild
    from app.tasks.kg_rebuild import rebuild_all_documents_task

    db = SessionLocal()
    try:
        existing = db.query(KgRebuild).filter(KgRebuild.version == KG_REBUILD_VERSION).first()
        if existing:
            return existing
        rebuild = KgRebuild(version=KG_REBUILD_VERSION, status="queued")
        db.add(rebuild)
        db.commit()
        db.refresh(rebuild)
        rebuild_all_documents_task.apply_async(args=[rebuild.id], countdown=10)
        return rebuild
    except Exception:
        db.rollback()
        return None
    finally:
        db.close()
