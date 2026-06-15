from pydantic import BaseModel, Field
from typing import Optional, Literal
from datetime import datetime


class KgExtractionSettings(BaseModel):
    chunk_min_chars: int = Field(default=120, ge=20, le=2000)
    chunk_size: int = Field(default=512, ge=100, le=5000)
    chunk_overlap: int = Field(default=128, ge=0, le=4999)
    relation_candidate_threshold: float = Field(default=0.2, ge=0, le=1)
    relation_auto_threshold: float = Field(default=0.8, ge=0, le=1)
    batch_chunks: int = Field(default=20, ge=1, le=100)
    max_parallel_batches: int = Field(default=8, ge=1, le=16)
    max_active_batches_per_document: int = Field(default=2, ge=1, le=16)
    batch_retry_limit: int = Field(default=2, ge=0, le=5)
    cross_relation_top_k: int = Field(default=30, ge=1, le=200)


# ──────────────── 系统设置（LLM / Embedding / 检索） ────────────────

class SettingsUpdate(BaseModel):
    llm_model: Optional[str] = None
    llm_api_base: Optional[str] = None
    llm_api_key: Optional[str] = None
    temperature: Optional[float] = Field(default=None, ge=0, le=2)
    top_p: Optional[float] = Field(default=None, ge=0, le=1)
    max_tokens: Optional[int] = Field(default=None, ge=1, le=32768)
    embedding_model: Optional[str] = None
    embedding_api_base: Optional[str] = None
    embedding_api_key: Optional[str] = None
    embedding_dimension: Optional[int] = Field(default=None, ge=64, le=8192)
    retrieval: Optional[dict] = None


# ──────────────── 模型档案 ────────────────

class ProfileCreate(BaseModel):
    type: Literal["llm", "embedding"]
    name: str = Field(..., max_length=100)
    api_url: str
    model: str
    dimension: Optional[int] = Field(default=None, ge=64, le=8192)
    api_key: Optional[str] = None


class ProfileUpdate(BaseModel):
    name: Optional[str] = None
    api_url: Optional[str] = None
    model: Optional[str] = None
    dimension: Optional[int] = Field(default=None, ge=64, le=8192)
    api_key: Optional[str] = None


class FetchModelsRequest(BaseModel):
    model_config = {"protected_namespaces": ()}

    api_url: str
    api_key: Optional[str] = None
    model_type: Literal["llm", "embedding"] = "llm"
    profile_id: Optional[str] = None
    use_saved_key: bool = False


# ──────────────── 通用配置 ────────────────

class SystemConfigCreate(BaseModel):
    config_key: str = Field(..., max_length=100)
    config_value: str
    description: Optional[str] = None


class SystemConfigUpdate(BaseModel):
    config_value: str
    description: Optional[str] = None


class SystemConfigResponse(BaseModel):
    id: int
    config_key: str
    config_value: str
    description: Optional[str] = None
    updated_by: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
