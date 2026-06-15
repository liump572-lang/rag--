"""运行时配置解析层。

系统配置以 `system_configs` 表为事实源，本模块在**调用时**把它解析成
LLM / Embedding / 检索 的运行时配置，使管理端「系统设置」里保存的配置能在
问答、KG 抽取、向量化等所有路径真正生效（不再只读环境变量）。

解析优先级（对齐 docker-em）：
  JSON 档案键(llm_config / embedding_model) → api_key_ref 指向的独立 key
  → 扁平键(deepseek_api_key / deepseek_api_base / llm_model …) → 环境变量(app.config.settings)

带 ~60s TTL 的进程内缓存；保存配置后由 system 模块调用 invalidate_config_cache() 失效。
"""

import json
import threading
import time
from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session

from app.config import settings

MASKED_VALUE = "********"
CACHE_TTL = 60.0

_cache_lock = threading.Lock()
_cache: dict[str, str] = {}
_cache_time: float = 0.0


@dataclass(frozen=True)
class LLMRuntimeConfig:
    api_url: str
    api_key: str
    model: str
    temperature: float
    top_p: float
    max_tokens: int
    timeout: int


@dataclass(frozen=True)
class EmbeddingRuntimeConfig:
    api_url: str
    api_key: str
    model: str
    dimension: int
    batch_size: int
    timeout: int


# ──────────────────────────── 原始配置加载 ────────────────────────────

def load_raw_config(db: Optional[Session] = None, *, force: bool = False) -> dict:
    """读取全部 system_configs 为 {key: value}，带进程内 TTL 缓存。"""
    global _cache, _cache_time
    now = time.monotonic()
    with _cache_lock:
        if not force and _cache and now - _cache_time < CACHE_TTL:
            return dict(_cache)

    from app.database import SessionLocal
    from app.models import SystemConfig

    own = db is None
    session = db or SessionLocal()
    try:
        rows = session.query(SystemConfig).all()
        raw = {row.config_key: row.config_value for row in rows}
    finally:
        if own:
            session.close()

    with _cache_lock:
        _cache = raw
        _cache_time = now
    return dict(raw)


def invalidate_config_cache() -> None:
    global _cache, _cache_time
    with _cache_lock:
        _cache = {}
        _cache_time = 0.0


# ──────────────────────────── 解析辅助 ────────────────────────────

def _json_value(raw: dict, key: str) -> dict:
    value = raw.get(key)
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _normalize_base_url(value: str) -> str:
    return (value or "").strip().rstrip("/")


def _is_real_key(key: str) -> bool:
    key = (key or "").strip()
    if not key:
        return False
    placeholders = ("your-deepseek-api-key", "sk-your", "your-api-key", "change-this")
    return not any(p in key for p in placeholders)


# ──────────────────────────── LLM / Embedding 解析 ────────────────────────────

def parse_llm_config(raw: dict) -> LLMRuntimeConfig:
    cfg = _json_value(raw, "llm_config")
    api_key_ref = cfg.get("api_key_ref")
    api_key = (
        (raw.get(api_key_ref) if api_key_ref else None)
        or cfg.get("api_key")
        or raw.get("llm_api_key")
        or raw.get("deepseek_api_key")
        or settings.deepseek_api_key
    )
    api_url = (
        cfg.get("api_url")
        or raw.get("llm_api_base")
        or raw.get("deepseek_api_base")
        or settings.deepseek_api_base
    )
    model = cfg.get("model") or raw.get("llm_model") or settings.llm_model
    return LLMRuntimeConfig(
        api_url=_normalize_base_url(api_url),
        api_key=(api_key or "").strip(),
        model=model,
        temperature=float(cfg.get("temperature", 0.7)),
        top_p=float(cfg.get("top_p", 0.9)),
        max_tokens=int(cfg.get("max_tokens", 4096)),
        timeout=300,
    )


def parse_embedding_config(raw: dict) -> EmbeddingRuntimeConfig:
    cfg = _json_value(raw, "embedding_model")
    # 兼容旧库：embedding_model 曾被存为纯字符串模型名
    legacy_model = None
    if not cfg:
        legacy = raw.get("embedding_model")
        if isinstance(legacy, str) and legacy.strip() and not legacy.strip().startswith(("{", "[")):
            legacy_model = legacy.strip()
    api_key_ref = cfg.get("api_key_ref")
    api_key = (
        (raw.get(api_key_ref) if api_key_ref else None)
        or cfg.get("api_key")
        or raw.get("embedding_api_key")
        or raw.get("deepseek_api_key")
        or settings.deepseek_api_key
    )
    api_url = (
        cfg.get("api_url")
        or raw.get("embedding_api_base")
        or raw.get("deepseek_api_base")
        or settings.deepseek_api_base
    )
    model = cfg.get("model") or legacy_model or settings.embedding_model
    return EmbeddingRuntimeConfig(
        api_url=_normalize_base_url(api_url),
        api_key=(api_key or "").strip(),
        model=model,
        dimension=int(cfg.get("dimension", settings.embedding_dim)),
        batch_size=int(cfg.get("batch_size", 32)),
        timeout=120,
    )


def get_llm_config(db: Optional[Session] = None) -> LLMRuntimeConfig:
    return parse_llm_config(load_raw_config(db))


def get_embedding_config(db: Optional[Session] = None) -> EmbeddingRuntimeConfig:
    return parse_embedding_config(load_raw_config(db))


def get_retrieval_config(db: Optional[Session] = None) -> dict:
    cfg = _json_value(load_raw_config(db), "retrieval_config")
    return {
        "top_k": int(cfg.get("top_k", 10)),
        "similarity_threshold": float(cfg.get("similarity_threshold", 0.75)),
        "vector_weight": float(cfg.get("vector_weight", 0.6)),
        "graph_weight": float(cfg.get("graph_weight", 0.4)),
    }


def has_remote_llm_config(db: Optional[Session] = None) -> bool:
    return _is_real_key(get_llm_config(db).api_key)


def has_remote_embedding_config(db: Optional[Session] = None) -> bool:
    return _is_real_key(get_embedding_config(db).api_key)


# ──────────────────────────── 脱敏 ────────────────────────────

def mask_config_value(key: str, value: str) -> str:
    """对 *_api_key（及历史 deepseek_api_key）做脱敏，用于 API 返回。"""
    if value and (key.endswith("_api_key") or key in {"deepseek_api_key"}):
        return MASKED_VALUE
    return value
