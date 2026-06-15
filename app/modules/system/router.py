from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.common.response import error_response, success_response
from app.common.runtime_config import invalidate_config_cache, mask_config_value
from app.database import get_db
from app.middleware.auth import get_current_user
from app.models import SystemConfig, User
from app.modules.system import service as system_service
from app.modules.system.schemas import (
    FetchModelsRequest,
    KgExtractionSettings,
    ProfileCreate,
    ProfileUpdate,
    SettingsUpdate,
    SystemConfigCreate,
    SystemConfigResponse,
    SystemConfigUpdate,
)
from app.modules.system.service import SystemConfigService

router = APIRouter()


def _require_admin(current_user: User):
    return current_user.role == "admin"


# ──────────────── KG 抽取参数（保留） ────────────────

@router.get("/kg-extraction-settings")
def get_kg_extraction_settings(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not _require_admin(current_user):
        return error_response(403, "无权限")
    from app.common.kg_settings import KG_SETTING_DEFAULTS, get_kg_settings
    values = get_kg_settings(db)
    return success_response(data={
        "chunk_min_chars": values["chunk.min_chars"],
        "chunk_size": values["chunk.size"],
        "chunk_overlap": values["chunk.overlap"],
        "relation_candidate_threshold": values["kg.relation_candidate_threshold"],
        "relation_auto_threshold": values["kg.relation_auto_threshold"],
        "batch_chunks": values.get("kg.batch_chunks", KG_SETTING_DEFAULTS["kg.batch_chunks"]),
        "max_parallel_batches": values.get("kg.max_parallel_batches", KG_SETTING_DEFAULTS["kg.max_parallel_batches"]),
        "max_active_batches_per_document": values.get(
            "kg.max_active_batches_per_document",
            KG_SETTING_DEFAULTS["kg.max_active_batches_per_document"],
        ),
        "batch_retry_limit": values.get("kg.batch_retry_limit", KG_SETTING_DEFAULTS["kg.batch_retry_limit"]),
        "cross_relation_top_k": values.get("kg.cross_relation_top_k", KG_SETTING_DEFAULTS["kg.cross_relation_top_k"]),
    })


@router.put("/kg-extraction-settings")
def update_kg_extraction_settings(
    body: KgExtractionSettings,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not _require_admin(current_user):
        return error_response(403, "无权限")
    from app.common.kg_settings import validate_kg_settings
    try:
        values = validate_kg_settings({
            "chunk.min_chars": body.chunk_min_chars,
            "chunk.size": body.chunk_size,
            "chunk.overlap": body.chunk_overlap,
            "kg.relation_candidate_threshold": body.relation_candidate_threshold,
            "kg.relation_auto_threshold": body.relation_auto_threshold,
            "kg.batch_chunks": body.batch_chunks,
            "kg.max_parallel_batches": body.max_parallel_batches,
            "kg.max_active_batches_per_document": body.max_active_batches_per_document,
            "kg.batch_retry_limit": body.batch_retry_limit,
            "kg.cross_relation_top_k": body.cross_relation_top_k,
        })
    except ValueError as exc:
        return error_response(400, str(exc))
    descriptions = {
        "chunk.min_chars": "文档最小切块大小",
        "chunk.size": "文档目标切块大小",
        "chunk.overlap": "文档切块重叠量",
        "kg.relation_candidate_threshold": "关系候选保留阈值",
        "kg.relation_auto_threshold": "关系自动入图阈值",
        "kg.batch_chunks": "每个并行抽取分段包含的切块数",
        "kg.max_parallel_batches": "图谱抽取最大并行分段数",
        "kg.max_active_batches_per_document": "单文档同时抽取的最大分段数",
        "kg.batch_retry_limit": "图谱抽取分段失败重试次数",
        "kg.cross_relation_top_k": "跨文档关系候选召回数量",
    }
    for key, value in values.items():
        row = db.query(SystemConfig).filter(SystemConfig.config_key == key).first()
        if row:
            row.config_value = str(value)
            row.updated_by = current_user.id
        else:
            db.add(SystemConfig(
                config_key=key,
                config_value=str(value),
                description=descriptions[key],
                updated_by=current_user.id,
            ))
    db.commit()
    invalidate_config_cache()
    return success_response(message="图谱抽取设置已保存")


# ──────────────── 系统设置（LLM / Embedding / 检索） ────────────────

@router.get("/settings")
def get_settings(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not _require_admin(current_user):
        return error_response(403, "无权限")
    return success_response(data=system_service.get_active_settings(db))


@router.put("/settings")
def update_settings(
    body: SettingsUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not _require_admin(current_user):
        return error_response(403, "无权限")
    system_service.update_active_settings(db, body, current_user.id)
    return success_response(message="设置已保存，下次调用即生效")


@router.get("/apikey-status")
def apikey_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not _require_admin(current_user):
        return error_response(403, "无权限")
    return success_response(data=system_service.apikey_status(db))


# ──────────────── 模型档案 ────────────────

@router.get("/profiles")
def list_profiles(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not _require_admin(current_user):
        return error_response(403, "无权限")
    return success_response(data=system_service.list_profiles(db))


@router.post("/profiles")
def create_profile(
    body: ProfileCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not _require_admin(current_user):
        return error_response(403, "无权限")
    return success_response(data=system_service.create_profile(db, body, current_user.id))


@router.put("/profiles/{profile_id}")
def update_profile(
    profile_id: str,
    body: ProfileUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not _require_admin(current_user):
        return error_response(403, "无权限")
    if not system_service.update_profile(db, profile_id, body, current_user.id):
        return error_response(404, "模型档案不存在")
    return success_response(message="已保存")


@router.delete("/profiles/{profile_id}")
def delete_profile(
    profile_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not _require_admin(current_user):
        return error_response(403, "无权限")
    if not system_service.delete_profile(db, profile_id, current_user.id):
        return error_response(404, "模型档案不存在")
    return success_response(message="已删除")


@router.post("/profiles/{profile_id}/activate")
def activate_profile(
    profile_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not _require_admin(current_user):
        return error_response(403, "无权限")
    if not system_service.activate_profile(db, profile_id, current_user.id):
        return error_response(404, "模型档案不存在")
    return success_response(message="已切换为当前使用配置")


@router.post("/fetch-models")
def fetch_models(
    body: FetchModelsRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not _require_admin(current_user):
        return error_response(403, "无权限")
    result = system_service.fetch_models(
        db,
        api_url=body.api_url,
        api_key=body.api_key or "",
        model_type=body.model_type,
        profile_id=body.profile_id,
        use_saved_key=body.use_saved_key,
    )
    return success_response(data=result)


# ──────────────── 通用配置 CRUD（脱敏） ────────────────

def _config_payload(cfg: SystemConfig) -> dict:
    data = SystemConfigResponse.model_validate(cfg).model_dump()
    data["config_value"] = mask_config_value(cfg.config_key, cfg.config_value)
    return data


@router.get("/configs")
def list_configs(
    keyword: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not _require_admin(current_user):
        return error_response(403, "无权限")
    items = SystemConfigService.list(db, keyword)
    return success_response(data=[_config_payload(c) for c in items])


@router.get("/configs/{config_id}")
def get_config(
    config_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not _require_admin(current_user):
        return error_response(403, "无权限")
    cfg = SystemConfigService.get(db, config_id)
    if not cfg:
        return error_response(404, "配置不存在")
    return success_response(data=_config_payload(cfg))


@router.post("/configs")
def create_config(
    body: SystemConfigCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not _require_admin(current_user):
        return error_response(403, "无权限")
    existing = SystemConfigService.get_by_key(db, body.config_key)
    if existing:
        return error_response(400, "配置键已存在")
    try:
        cfg = SystemConfigService.create(db, body, current_user.id)
    except ValueError as exc:
        return error_response(400, str(exc))
    return success_response(data=_config_payload(cfg))


@router.put("/configs/{config_id}")
def update_config(
    config_id: int,
    body: SystemConfigUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not _require_admin(current_user):
        return error_response(403, "无权限")
    try:
        cfg = SystemConfigService.update(db, config_id, body, current_user.id)
    except ValueError as exc:
        return error_response(400, str(exc))
    if not cfg:
        return error_response(404, "配置不存在")
    return success_response(data=_config_payload(cfg))


@router.delete("/configs/{config_id}")
def delete_config(
    config_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not _require_admin(current_user):
        return error_response(403, "无权限")
    ok = SystemConfigService.delete(db, config_id)
    if not ok:
        return error_response(404, "配置不存在")
    return success_response(message="已删除")
