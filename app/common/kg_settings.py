from sqlalchemy.orm import Session

from app.models import SystemConfig


KG_SETTING_DEFAULTS = {
    "chunk.min_chars": 120,
    "chunk.size": 512,
    "chunk.overlap": 128,
    "kg.relation_candidate_threshold": 0.2,
    "kg.relation_auto_threshold": 0.8,
    "kg.batch_chunks": 20,
    "kg.max_parallel_batches": 8,
    "kg.max_active_batches_per_document": 2,
    "kg.batch_retry_limit": 2,
    "kg.cross_relation_top_k": 30,
}


def get_kg_settings(db: Session) -> dict:
    rows = db.query(SystemConfig).filter(SystemConfig.config_key.in_(KG_SETTING_DEFAULTS)).all()
    values = dict(KG_SETTING_DEFAULTS)
    for row in rows:
        default = KG_SETTING_DEFAULTS[row.config_key]
        try:
            values[row.config_key] = int(row.config_value) if isinstance(default, int) else float(row.config_value)
        except (TypeError, ValueError):
            values[row.config_key] = default
    return validate_kg_settings(values)


def validate_kg_settings(values: dict) -> dict:
    min_chars = int(values["chunk.min_chars"])
    chunk_size = int(values["chunk.size"])
    overlap = int(values["chunk.overlap"])
    candidate = float(values["kg.relation_candidate_threshold"])
    automatic = float(values["kg.relation_auto_threshold"])
    batch_chunks = int(values["kg.batch_chunks"])
    max_parallel_batches = int(values["kg.max_parallel_batches"])
    max_active_batches_per_document = int(values["kg.max_active_batches_per_document"])
    batch_retry_limit = int(values["kg.batch_retry_limit"])
    cross_relation_top_k = int(values["kg.cross_relation_top_k"])

    if not 20 <= min_chars <= 2000:
        raise ValueError("最小切块大小必须在 20 至 2000 之间")
    if not 100 <= chunk_size <= 5000:
        raise ValueError("目标切块大小必须在 100 至 5000 之间")
    if min_chars >= chunk_size:
        raise ValueError("最小切块大小必须小于目标切块大小")
    if not 0 <= overlap < chunk_size:
        raise ValueError("重叠大小必须大于等于 0 且小于目标切块大小")
    if not 0 <= candidate <= automatic <= 1:
        raise ValueError("候选阈值必须在 0 至自动入图阈值之间")
    if not 1 <= batch_chunks <= 100:
        raise ValueError("每个抽取分段的切块数必须在 1 至 100 之间")
    if not 1 <= max_parallel_batches <= 16:
        raise ValueError("并行抽取分段数必须在 1 至 16 之间")
    if not 1 <= max_active_batches_per_document <= max_parallel_batches:
        raise ValueError("单文档并行分段数必须在 1 至总并行分段数之间")
    if not 0 <= batch_retry_limit <= 5:
        raise ValueError("抽取分段重试次数必须在 0 至 5 之间")
    if not 1 <= cross_relation_top_k <= 200:
        raise ValueError("跨文档关系候选数必须在 1 至 200 之间")
    return {
        "chunk.min_chars": min_chars,
        "chunk.size": chunk_size,
        "chunk.overlap": overlap,
        "kg.relation_candidate_threshold": candidate,
        "kg.relation_auto_threshold": automatic,
        "kg.batch_chunks": batch_chunks,
        "kg.max_parallel_batches": max_parallel_batches,
        "kg.max_active_batches_per_document": max_active_batches_per_document,
        "kg.batch_retry_limit": batch_retry_limit,
        "kg.cross_relation_top_k": cross_relation_top_k,
    }
