from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # MySQL
    database_url: str = "mysql+pymysql://qa_app:qa_app_pass@mysql:3306/knowledge_qa_system?charset=utf8mb4"

    # Redis
    redis_host: str = "redis"
    redis_port: int = 6379
    celery_broker_url: str = "redis://redis:6379/1"
    celery_result_backend: str = "redis://redis:6379/1"

    # Neo4j
    neo4j_uri: str = "bolt://neo4j:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "neo4j_password"

    # ChromaDB
    chroma_host: str = "chromadb"
    chroma_port: int = 8000

    # DeepSeek LLM
    deepseek_api_key: str = ""
    deepseek_api_base: str = "https://api.deepseek.com/v1"
    llm_model: str = "deepseek-v4-flash"
    embedding_model: str = "deepseek-embedding"
    embedding_dim: int = 1024

    # JWT
    jwt_secret_key: str = "change-this-to-a-random-secret-key"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    # Upload
    upload_dir: str = "/app/uploads"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()
