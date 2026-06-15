import json
import uuid
from typing import Optional

from sqlalchemy.orm import Session

from app.common.runtime_config import (
    MASKED_VALUE,
    get_embedding_config,
    get_llm_config,
    get_retrieval_config,
    invalidate_config_cache,
    mask_config_value,
)
from app.models import SystemConfig


# ──────────────────────────── 通用配置 CRUD（保留） ────────────────────────────

def _validate_kg_config_change(db: Session, key: str, value: str):
    from app.common.kg_settings import KG_SETTING_DEFAULTS, validate_kg_settings
    if key not in KG_SETTING_DEFAULTS:
        return
    values = dict(KG_SETTING_DEFAULTS)
    rows = db.query(SystemConfig).filter(SystemConfig.config_key.in_(KG_SETTING_DEFAULTS)).all()
    for row in rows:
        values[row.config_key] = row.config_value
    values[key] = value
    validate_kg_settings(values)


class SystemConfigService:

    @staticmethod
    def list(db: Session, keyword: str = None):
        query = db.query(SystemConfig)
        if keyword:
            query = query.filter(SystemConfig.config_key.like(f"%{keyword}%"))
        return query.order_by(SystemConfig.id).all()

    @staticmethod
    def get(db: Session, config_id: int) -> Optional[SystemConfig]:
        return db.query(SystemConfig).filter(SystemConfig.id == config_id).first()

    @staticmethod
    def get_by_key(db: Session, key: str) -> Optional[SystemConfig]:
        return db.query(SystemConfig).filter(SystemConfig.config_key == key).first()

    @staticmethod
    def create(db: Session, data, user_id: int) -> SystemConfig:
        _validate_kg_config_change(db, data.config_key, data.config_value)
        cfg = SystemConfig(
            config_key=data.config_key,
            config_value=data.config_value,
            description=data.description,
            updated_by=user_id,
        )
        db.add(cfg)
        db.commit()
        db.refresh(cfg)
        invalidate_config_cache()
        return cfg

    @staticmethod
    def update(db: Session, config_id: int, data, user_id: int) -> Optional[SystemConfig]:
        cfg = db.query(SystemConfig).filter(SystemConfig.id == config_id).first()
        if not cfg:
            return None
        _validate_kg_config_change(db, cfg.config_key, data.config_value)
        cfg.config_value = data.config_value
        if data.description is not None:
            cfg.description = data.description
        cfg.updated_by = user_id
        db.commit()
        db.refresh(cfg)
        invalidate_config_cache()
        return cfg

    @staticmethod
    def delete(db: Session, config_id: int) -> bool:
        cfg = db.query(SystemConfig).filter(SystemConfig.id == config_id).first()
        if not cfg:
            return False
        db.delete(cfg)
        db.commit()
        invalidate_config_cache()
        return True


# ──────────────────────────── 存取辅助 ────────────────────────────

def _get(db: Session, key: str) -> Optional[str]:
    row = db.query(SystemConfig).filter(SystemConfig.config_key == key).first()
    return row.config_value if row else None


def _get_json(db: Session, key: str, default):
    raw = _get(db, key)
    if not raw:
        return default
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return default


def _upsert(db: Session, key: str, value: str, user_id: int = None, description: str = None):
    row = db.query(SystemConfig).filter(SystemConfig.config_key == key).first()
    if row:
        row.config_value = value
        if description is not None:
            row.description = description
        if user_id is not None:
            row.updated_by = user_id
    else:
        db.add(SystemConfig(config_key=key, config_value=value, description=description, updated_by=user_id))


def _key_is_real(value: Optional[str]) -> bool:
    value = (value or "").strip()
    if not value:
        return False
    return not any(p in value for p in ("your-deepseek-api-key", "sk-your", "your-api-key", "change-this"))


# ──────────────────────────── 模型档案（profiles） ────────────────────────────

def _profile_key_name(profile_type: str, profile_id: str) -> str:
    return f"{profile_type}_profile_{profile_id}_api_key"


def list_profiles(db: Session) -> list[dict]:
    profiles = _get_json(db, "model_profiles", [])
    if not isinstance(profiles, list):
        profiles = []
    llm_active = _get_json(db, "llm_config", {})
    emb_active = _get_json(db, "embedding_model", {})
    active_refs = {
        "llm": (llm_active or {}).get("api_key_ref"),
        "embedding": (emb_active or {}).get("api_key_ref"),
    }
    active_models = {
        "llm": ((llm_active or {}).get("model"), (llm_active or {}).get("api_url")),
        "embedding": ((emb_active or {}).get("model"), (emb_active or {}).get("api_url")),
    }
    out = []
    for p in profiles:
        if not isinstance(p, dict):
            continue
        ptype = p.get("type", "llm")
        pid = p.get("id", "")
        key_name = _profile_key_name(ptype, pid)
        is_active = active_refs.get(ptype) == key_name or (
            active_models.get(ptype) == (p.get("model"), p.get("api_url"))
        )
        out.append({
            "id": pid,
            "type": ptype,
            "name": p.get("name", ""),
            "api_url": p.get("api_url", ""),
            "model": p.get("model", ""),
            "dimension": p.get("dimension"),
            "api_key_configured": _key_is_real(_get(db, key_name)),
            "active": bool(is_active),
        })
    return out


def create_profile(db: Session, data, user_id: int) -> dict:
    profiles = _get_json(db, "model_profiles", [])
    if not isinstance(profiles, list):
        profiles = []
    pid = uuid.uuid4().hex[:8]
    profile = {
        "id": pid,
        "type": data.type,
        "name": data.name,
        "api_url": (data.api_url or "").strip().rstrip("/"),
        "model": data.model,
    }
    if data.type == "embedding" and data.dimension:
        profile["dimension"] = int(data.dimension)
    profiles.append(profile)
    _upsert(db, "model_profiles", json.dumps(profiles, ensure_ascii=False), user_id, "已保存模型配置")
    if data.api_key:
        _upsert(db, _profile_key_name(data.type, pid), data.api_key, user_id, f"{data.type} 档案 {data.name} 的 API Key")
    db.commit()
    invalidate_config_cache()
    return {"id": pid}


def update_profile(db: Session, profile_id: str, data, user_id: int) -> bool:
    profiles = _get_json(db, "model_profiles", [])
    found = None
    for p in profiles if isinstance(profiles, list) else []:
        if isinstance(p, dict) and p.get("id") == profile_id:
            found = p
            break
    if not found:
        return False
    if data.name is not None:
        found["name"] = data.name
    if data.api_url is not None:
        found["api_url"] = data.api_url.strip().rstrip("/")
    if data.model is not None:
        found["model"] = data.model
    if data.dimension is not None and found.get("type") == "embedding":
        found["dimension"] = int(data.dimension)
    _upsert(db, "model_profiles", json.dumps(profiles, ensure_ascii=False), user_id)
    if data.api_key:
        _upsert(db, _profile_key_name(found.get("type", "llm"), profile_id), data.api_key, user_id)
    db.commit()
    invalidate_config_cache()
    # 若该档案正处于激活态，刷新激活配置以反映新值
    _refresh_active_if_profile(db, found, user_id)
    return True


def delete_profile(db: Session, profile_id: str, user_id: int) -> bool:
    profiles = _get_json(db, "model_profiles", [])
    if not isinstance(profiles, list):
        return False
    remaining = [p for p in profiles if not (isinstance(p, dict) and p.get("id") == profile_id)]
    if len(remaining) == len(profiles):
        return False
    removed = next((p for p in profiles if isinstance(p, dict) and p.get("id") == profile_id), {})
    _upsert(db, "model_profiles", json.dumps(remaining, ensure_ascii=False), user_id)
    key_name = _profile_key_name(removed.get("type", "llm"), profile_id)
    key_row = db.query(SystemConfig).filter(SystemConfig.config_key == key_name).first()
    if key_row:
        db.delete(key_row)
    db.commit()
    invalidate_config_cache()
    return True


def activate_profile(db: Session, profile_id: str, user_id: int) -> bool:
    profiles = _get_json(db, "model_profiles", [])
    profile = next((p for p in profiles if isinstance(p, dict) and p.get("id") == profile_id), None) if isinstance(profiles, list) else None
    if not profile:
        return False
    _refresh_active_if_profile(db, profile, user_id, force=True)
    db.commit()
    invalidate_config_cache()
    from app.common.llm_client import invalidate_llm_client
    invalidate_llm_client()
    return True


def _refresh_active_if_profile(db: Session, profile: dict, user_id: int, force: bool = False):
    ptype = profile.get("type", "llm")
    pid = profile.get("id", "")
    key_ref = _profile_key_name(ptype, pid)
    if ptype == "llm":
        current = _get_json(db, "llm_config", {}) or {}
        if not force and current.get("api_key_ref") != key_ref:
            return
        new_cfg = {
            "api_url": profile.get("api_url", ""),
            "model": profile.get("model", ""),
            "api_key_ref": key_ref,
            "temperature": current.get("temperature", 0.7),
            "top_p": current.get("top_p", 0.9),
            "max_tokens": current.get("max_tokens", 4096),
        }
        _upsert(db, "llm_config", json.dumps(new_cfg, ensure_ascii=False), user_id, "LLM 模型配置")
    else:
        current = _get_json(db, "embedding_model", {}) or {}
        if not force and current.get("api_key_ref") != key_ref:
            return
        new_cfg = {
            "api_url": profile.get("api_url", ""),
            "model": profile.get("model", ""),
            "api_key_ref": key_ref,
            "dimension": int(profile.get("dimension") or current.get("dimension") or 1024),
            "batch_size": current.get("batch_size", 32),
        }
        _upsert(db, "embedding_model", json.dumps(new_cfg, ensure_ascii=False), user_id, "Embedding 模型配置")


# ──────────────────────────── 当前生效配置（settings） ────────────────────────────

def get_active_settings(db: Session) -> dict:
    llm = get_llm_config(db)
    emb = get_embedding_config(db)
    retrieval = get_retrieval_config(db)
    return {
        "llm": {
            "model": llm.model,
            "api_base": llm.api_url,
            "api_key_masked": MASKED_VALUE if _key_is_real(llm.api_key) else "未配置",
            "temperature": llm.temperature,
            "top_p": llm.top_p,
            "max_tokens": llm.max_tokens,
        },
        "embedding": {
            "model": emb.model,
            "api_base": emb.api_url,
            "api_key_masked": MASKED_VALUE if _key_is_real(emb.api_key) else "未配置",
            "dimension": emb.dimension,
        },
        "retrieval": retrieval,
    }


def update_active_settings(db: Session, body, user_id: int) -> None:
    # LLM
    llm_cfg = _get_json(db, "llm_config", {}) or {}
    llm_cfg.setdefault("api_key_ref", "llm_api_key")
    if body.llm_model is not None:
        llm_cfg["model"] = body.llm_model
    if body.llm_api_base is not None:
        llm_cfg["api_url"] = body.llm_api_base.strip().rstrip("/")
    if body.temperature is not None:
        llm_cfg["temperature"] = float(body.temperature)
    if body.top_p is not None:
        llm_cfg["top_p"] = float(body.top_p)
    if body.max_tokens is not None:
        llm_cfg["max_tokens"] = int(body.max_tokens)
    _upsert(db, "llm_config", json.dumps(llm_cfg, ensure_ascii=False), user_id, "LLM 模型配置")
    if body.llm_api_key:
        _upsert(db, llm_cfg["api_key_ref"], body.llm_api_key, user_id, "LLM API Key")

    # Embedding
    emb_cfg = _get_json(db, "embedding_model", {}) or {}
    emb_cfg.setdefault("api_key_ref", "embedding_api_key")
    if body.embedding_model is not None:
        emb_cfg["model"] = body.embedding_model
    if body.embedding_api_base is not None:
        emb_cfg["api_url"] = body.embedding_api_base.strip().rstrip("/")
    if body.embedding_dimension is not None:
        emb_cfg["dimension"] = int(body.embedding_dimension)
    _upsert(db, "embedding_model", json.dumps(emb_cfg, ensure_ascii=False), user_id, "Embedding 模型配置")
    if body.embedding_api_key:
        _upsert(db, emb_cfg["api_key_ref"], body.embedding_api_key, user_id, "Embedding API Key")

    # Retrieval
    if body.retrieval is not None:
        retrieval = get_retrieval_config(db)
        retrieval.update({k: v for k, v in body.retrieval.items() if v is not None})
        _upsert(db, "retrieval_config", json.dumps(retrieval, ensure_ascii=False), user_id, "检索配置")

    db.commit()
    invalidate_config_cache()
    from app.common.llm_client import invalidate_llm_client
    invalidate_llm_client()


def apikey_status(db: Session) -> dict:
    return {
        "llm_api_key_configured": _key_is_real(get_llm_config(db).api_key),
        "embedding_api_key_configured": _key_is_real(get_embedding_config(db).api_key),
    }


# ──────────────────────────── 动态拉取模型列表 ────────────────────────────

def _resolve_saved_key(db: Session, model_type: str, profile_id: Optional[str]) -> str:
    if profile_id:
        key = _get(db, _profile_key_name(model_type, profile_id))
        if key:
            return key
    # 回退当前激活配置解析出的 key
    cfg = get_llm_config(db) if model_type == "llm" else get_embedding_config(db)
    return cfg.api_key or ""


def fetch_models(db: Session, api_url: str, api_key: str, model_type: str = "llm",
                 profile_id: str = None, use_saved_key: bool = False) -> dict:
    from openai import OpenAI

    api_url = (api_url or "").strip().rstrip("/")
    if not api_url:
        return {"models": [], "error": "请填写 API Base URL"}

    key = (api_key or "").strip()
    if not key and use_saved_key:
        key = _resolve_saved_key(db, model_type, profile_id)

    def _list(use_key: str):
        client = OpenAI(api_key=use_key or "not-set", base_url=api_url, timeout=15, max_retries=0)
        resp = client.models.list()
        return sorted({getattr(m, "id", "") for m in resp.data if getattr(m, "id", "")})

    try:
        try:
            models = _list(key)
        except Exception as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None) or getattr(exc, "status_code", None)
            if status in (401, 403) and not key:
                retry_key = _resolve_saved_key(db, model_type, profile_id)
                if not retry_key:
                    raise
                models = _list(retry_key)
            else:
                raise
        return {"models": models, "error": None}
    except Exception as exc:
        status = getattr(getattr(exc, "response", None), "status_code", None) or getattr(exc, "status_code", None)
        is_deepseek = "api.deepseek.com" in api_url.lower()
        if status in (401, 403):
            if is_deepseek:
                return {"models": [], "error": "DeepSeek API Key 无效，请确认使用 DeepSeek 平台生成的 Key。"}
            return {"models": [], "error": "该服务的模型列表需要有效 API Key，请填写当前地址对应的 Key 后重试"}
        if status == 404:
            return {"models": [], "error": "未找到模型列表接口，请检查 API Base URL 是否为 OpenAI 兼容地址"}
        return {"models": [], "error": f"获取模型列表失败：{str(exc)[:200]}"}
