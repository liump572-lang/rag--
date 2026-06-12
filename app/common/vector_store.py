import hashlib
import math
import re
import time
from typing import List, Optional

import chromadb
from chromadb.config import Settings as ChromaSettings

from app.common.llm_client import embed_text
from app.config import settings

CHROMA_COLLECTION = "document_chunks"
EMBEDDING_DIM = 384  # Keep compatible with the existing Chroma collection.
EMBED_BATCH_SIZE = 20
EMBED_RETRY_DELAY = 2

_client = None
_remote_embeddings_available = True


def get_chroma_client():
    global _client
    if _client is None:
        _client = chromadb.HttpClient(
            host=settings.chroma_host,
            port=settings.chroma_port,
            settings=ChromaSettings(allow_reset=True, anonymized_telemetry=False),
        )
    return _client


def get_or_create_collection():
    client = get_chroma_client()
    try:
        coll = client.get_collection(CHROMA_COLLECTION)
        return coll
    except Exception:
        return client.create_collection(
            CHROMA_COLLECTION,
            metadata={"hnsw:space": "cosine"},
        )


def _embed_batch(texts: List[str]) -> List[List[float]]:
    """Embed a list of texts using DeepSeek API with retry."""
    global _remote_embeddings_available
    if not _remote_embeddings_available:
        return [_local_hash_embedding(text) for text in texts]

    embeddings = []
    for text in texts:
        for attempt in range(3):
            try:
                vec = embed_text(text)
                if len(vec) != EMBEDDING_DIM:
                    _remote_embeddings_available = False
                    return [_local_hash_embedding(item) for item in texts]
                embeddings.append(vec)
                break
            except Exception as e:
                if _is_not_found_error(e):
                    _remote_embeddings_available = False
                    return [_local_hash_embedding(item) for item in texts]
                if attempt == 2:
                    return [_local_hash_embedding(item) for item in texts]
                time.sleep(EMBED_RETRY_DELAY * (attempt + 1))
    return embeddings


def _is_not_found_error(error: Exception) -> bool:
    status_code = getattr(error, "status_code", None)
    if status_code is None:
        status_code = getattr(getattr(error, "response", None), "status_code", None)
    return status_code == 404


def _local_hash_embedding(text: str) -> List[float]:
    """Create a deterministic offline vector for retrieval when the remote API is unavailable."""
    vector = [0.0] * EMBEDDING_DIM
    normalized = text.lower()
    tokens = re.findall(r"[\u4e00-\u9fff]|[a-z0-9_]+", normalized)
    for token in tokens:
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
        value = int.from_bytes(digest, "big")
        index = value % EMBEDDING_DIM
        vector[index] += -1.0 if value & 1 else 1.0

    norm = math.sqrt(sum(value * value for value in vector))
    if norm:
        return [value / norm for value in vector]
    return vector


def add_chunks(chunks: List[dict]) -> List[str]:
    """
    Add document chunks to ChromaDB with DeepSeek embeddings.
    Processes in batches to avoid overwhelming the API.
    """
    collection = get_or_create_collection()
    all_ids = []

    for i in range(0, len(chunks), EMBED_BATCH_SIZE):
        batch = chunks[i:i + EMBED_BATCH_SIZE]
        ids = [str(c["id"]) for c in batch]
        documents = [c["content"] for c in batch]
        metadatas = [
            {"document_id": c["document_id"], "chunk_index": c["chunk_index"]}
            for c in batch
        ]

        embeddings = _embed_batch(documents)
        collection.add(
            ids=ids,
            documents=documents,
            embeddings=embeddings,
            metadatas=metadatas,
        )

        all_ids.extend(ids)

    return all_ids


def delete_document_chunks(document_id: int, strict: bool = False) -> bool:
    collection = get_or_create_collection()
    try:
        results = collection.get(where={"document_id": document_id})
        if results["ids"]:
            collection.delete(ids=results["ids"])
        return True
    except Exception:
        if strict:
            raise
        return False


def search_chunks(
    query: str,
    top_k: int = 10,
    where: Optional[dict] = None,
    subject_id: Optional[int] = None,
) -> List[dict]:
    """
    Search chunks using DeepSeek embedding for the query.
    Falls back to ChromaDB default embedding if DeepSeek fails.
    """
    collection = get_or_create_collection()

    try:
        query_embedding = embed_text(query)
        if len(query_embedding) != EMBEDDING_DIM:
            raise ValueError("remote embedding dimension is incompatible with the collection")
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where=where,
        )
    except Exception as error:
        if _is_not_found_error(error):
            global _remote_embeddings_available
            _remote_embeddings_available = False
        # Keep retrieval available without downloading Chroma's default model.
        results = collection.query(
            query_embeddings=[_local_hash_embedding(query)],
            n_results=top_k,
            where=where,
        )

    hits = []
    if results.get("ids") and results["ids"][0]:
        for i in range(len(results["ids"][0])):
            raw_distance = (
                results["distances"][0][i] if results.get("distances") else 0
            )
            if raw_distance is not None:
                score = 1.0 / (1.0 + raw_distance)
            else:
                score = 0.0
            hits.append({
                "id": int(results["ids"][0][i]),
                "content": results["documents"][0][i],
                "metadata": results["metadatas"][0][i] if results.get("metadatas") else {},
                "score": round(score, 4),
            })

    return hits
