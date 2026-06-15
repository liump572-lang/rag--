import hashlib
import math
import re
import time
from typing import List, Optional

import chromadb
from chromadb.config import Settings as ChromaSettings
from sqlalchemy.orm import Session

from app.common.llm_client import embed_text
from app.common.runtime_config import get_embedding_config, has_remote_embedding_config
from app.config import settings

EMBED_BATCH_SIZE = 20
EMBED_RETRY_DELAY = 2
COLLECTION_PREFIX = "document_chunks_v"

_client = None


def get_chroma_client():
    global _client
    if _client is None:
        _client = chromadb.HttpClient(
            host=settings.chroma_host,
            port=settings.chroma_port,
            settings=ChromaSettings(allow_reset=True, anonymized_telemetry=False),
        )
    return _client


def _collection_name(dim: int) -> str:
    # 维度编码进集合名：切换 embedding 维度即换集合，避免维度不匹配错误。
    return f"{COLLECTION_PREFIX}{dim}"


def get_or_create_collection(dim: int):
    client = get_chroma_client()
    name = _collection_name(dim)
    try:
        return client.get_collection(name)
    except Exception:
        return client.create_collection(name, metadata={"hnsw:space": "cosine"})


def _is_not_found_error(error: Exception) -> bool:
    status_code = getattr(error, "status_code", None)
    if status_code is None:
        status_code = getattr(getattr(error, "response", None), "status_code", None)
    return status_code == 404


def _local_hash_embedding(text: str, dim: int) -> List[float]:
    """远端 embedding 不可用时的确定性离线向量，保证检索仍可用。"""
    dim = max(128, int(dim or 1024))
    vector = [0.0] * dim
    normalized = (text or "").lower()
    tokens = re.findall(r"[一-鿿]|[a-z0-9_]+", normalized)
    for token in tokens:
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
        value = int.from_bytes(digest, "big")
        index = value % dim
        vector[index] += -1.0 if value & 1 else 1.0
    norm = math.sqrt(sum(value * value for value in vector))
    if norm:
        return [value / norm for value in vector]
    return vector


def _embed_batch(texts: List[str], dim: int, db: Optional[Session] = None) -> List[List[float]]:
    """用运行时 Embedding 配置批量向量化，失败回退本地哈希（保证维度一致）。"""
    if not has_remote_embedding_config(db):
        return [_local_hash_embedding(text, dim) for text in texts]

    embeddings = []
    for text in texts:
        for attempt in range(3):
            try:
                vec = embed_text(text, db=db)
                if len(vec) != dim:
                    # 维度与当前集合不一致：整批回退本地哈希，避免写入失败/污染。
                    return [_local_hash_embedding(item, dim) for item in texts]
                embeddings.append(vec)
                break
            except Exception as e:
                if _is_not_found_error(e) or attempt == 2:
                    return [_local_hash_embedding(item, dim) for item in texts]
                time.sleep(EMBED_RETRY_DELAY * (attempt + 1))
    return embeddings


def add_chunks(chunks: List[dict], db: Optional[Session] = None) -> List[str]:
    """把文档分片写入 ChromaDB（按当前 Embedding 配置的维度选择集合）。"""
    cfg = get_embedding_config(db)
    dim = cfg.dimension
    collection = get_or_create_collection(dim)
    all_ids = []

    for i in range(0, len(chunks), EMBED_BATCH_SIZE):
        batch = chunks[i:i + EMBED_BATCH_SIZE]
        ids = [str(c["id"]) for c in batch]
        documents = [c["content"] for c in batch]
        metadatas = [
            {"document_id": c["document_id"], "chunk_index": c["chunk_index"]}
            for c in batch
        ]
        embeddings = _embed_batch(documents, dim, db=db)
        collection.add(ids=ids, documents=documents, embeddings=embeddings, metadatas=metadatas)
        all_ids.extend(ids)

    return all_ids


def delete_document_chunks(document_id: int, strict: bool = False, db: Optional[Session] = None) -> bool:
    """删除某文档在所有 document_chunks_v* 集合里的向量（兼容维度切换历史）。"""
    client = get_chroma_client()
    try:
        collections = client.list_collections()
    except Exception:
        if strict:
            raise
        return False

    ok = True
    for coll in collections:
        name = getattr(coll, "name", coll)
        if not str(name).startswith(COLLECTION_PREFIX):
            continue
        try:
            collection = client.get_collection(name)
            results = collection.get(where={"document_id": document_id})
            if results.get("ids"):
                collection.delete(ids=results["ids"])
        except Exception:
            ok = False
            if strict:
                raise
    return ok


def search_chunks(
    query: str,
    top_k: int = 10,
    where: Optional[dict] = None,
    subject_id: Optional[int] = None,
    db: Optional[Session] = None,
) -> List[dict]:
    """语义检索；远端 embedding 不可用或维度不符时回退本地哈希向量。"""
    cfg = get_embedding_config(db)
    dim = cfg.dimension
    collection = get_or_create_collection(dim)

    try:
        if not has_remote_embedding_config(db):
            raise ValueError("remote embedding api key is not configured")
        query_embedding = embed_text(query, db=db)
        if len(query_embedding) != dim:
            raise ValueError("remote embedding dimension is incompatible with the collection")
        results = collection.query(query_embeddings=[query_embedding], n_results=top_k, where=where)
    except Exception:
        results = collection.query(
            query_embeddings=[_local_hash_embedding(query, dim)],
            n_results=top_k,
            where=where,
        )

    hits = []
    if results.get("ids") and results["ids"][0]:
        for i in range(len(results["ids"][0])):
            raw_distance = results["distances"][0][i] if results.get("distances") else 0
            score = 1.0 / (1.0 + raw_distance) if raw_distance is not None else 0.0
            hits.append({
                "id": int(results["ids"][0][i]),
                "content": results["documents"][0][i],
                "metadata": results["metadatas"][0][i] if results.get("metadatas") else {},
                "score": round(score, 4),
            })

    return hits
