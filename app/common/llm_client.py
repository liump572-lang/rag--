"""LLM / Embedding 客户端。

默认从运行时配置（system_configs，见 app/common/runtime_config.py）解析
api_key / base_url / model，使管理端保存的配置在所有调用路径生效。
LLM 与 Embedding 使用相互独立的客户端，端点/密钥/模型可不同。
"""

import threading
from typing import Optional

from openai import OpenAI
from sqlalchemy.orm import Session

from app.common.runtime_config import get_embedding_config, get_llm_config

_lock = threading.Lock()
_llm_client: Optional[OpenAI] = None
_llm_signature = None
_embed_client: Optional[OpenAI] = None
_embed_signature = None


def get_llm_client(
    db: Optional[Session] = None,
    api_key: Optional[str] = None,
    api_base: Optional[str] = None,
) -> OpenAI:
    """构建/复用 LLM 客户端；未显式传 key/base 时从运行时配置解析。"""
    global _llm_client, _llm_signature
    if api_key is None or api_base is None:
        cfg = get_llm_config(db)
        api_key = api_key or cfg.api_key
        api_base = api_base or cfg.api_url
    signature = (api_key, api_base)
    with _lock:
        if _llm_client is None or signature != _llm_signature:
            _llm_client = OpenAI(
                api_key=api_key or "not-configured",
                base_url=api_base or None,
                timeout=300,
                max_retries=3,
            )
            _llm_signature = signature
        return _llm_client


def get_embedding_client(db: Optional[Session] = None):
    """构建/复用 Embedding 客户端，返回 (client, model)。"""
    global _embed_client, _embed_signature
    cfg = get_embedding_config(db)
    signature = (cfg.api_key, cfg.api_url)
    with _lock:
        if _embed_client is None or signature != _embed_signature:
            _embed_client = OpenAI(
                api_key=cfg.api_key or "not-configured",
                base_url=cfg.api_url or None,
                timeout=cfg.timeout,
                max_retries=2,
            )
            _embed_signature = signature
        return _embed_client, cfg.model


def invalidate_llm_client() -> None:
    """配置变更后清空缓存的客户端（LLM 与 Embedding）。"""
    global _llm_client, _llm_signature, _embed_client, _embed_signature
    with _lock:
        _llm_client = None
        _llm_signature = None
        _embed_client = None
        _embed_signature = None


def chat_stream(
    messages: list,
    db: Optional[Session] = None,
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    api_base: Optional[str] = None,
    **kwargs,
):
    cfg = get_llm_config(db)
    client = get_llm_client(db=db, api_key=api_key or cfg.api_key, api_base=api_base or cfg.api_url)
    return client.chat.completions.create(
        model=model or cfg.model,
        messages=messages,
        stream=True,
        temperature=kwargs.get("temperature", cfg.temperature),
        max_tokens=kwargs.get("max_tokens", cfg.max_tokens),
        timeout=300,
    )


def chat(
    messages: list,
    db: Optional[Session] = None,
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    api_base: Optional[str] = None,
    **kwargs,
) -> str:
    cfg = get_llm_config(db)
    client = get_llm_client(db=db, api_key=api_key or cfg.api_key, api_base=api_base or cfg.api_url)
    resp = client.chat.completions.create(
        model=model or cfg.model,
        messages=messages,
        stream=False,
        temperature=kwargs.get("temperature", cfg.temperature),
        max_tokens=kwargs.get("max_tokens", cfg.max_tokens),
        timeout=300,
    )
    msg = resp.choices[0].message
    return msg.content or getattr(msg, "reasoning_content", None) or ""


def embed_text(text: str, db: Optional[Session] = None) -> list:
    client, model = get_embedding_client(db)
    resp = client.embeddings.create(model=model, input=text, timeout=120)
    return resp.data[0].embedding
