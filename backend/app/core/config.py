from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "robot-llm"
    app_env: Literal["development", "test", "production"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    database_url: str | None = None
    redis_url: str | None = None
    minio_endpoint: str | None = None
    minio_access_key: str | None = None
    minio_secret_key: str | None = None
    minio_secure: bool = False
    minio_bucket: str = "knowledge-documents"
    knowledge_repository: str = "https://github.com/eldiyar1710/robot-llm-3.11.26"
    knowledge_branch: str = "main"
    github_token: str | None = None
    embedding_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    embedding_cache_dir: str = ".models"
    rag_top_k: int = 5
    rag_max_distance: float = 0.45
    llm_url: str = "http://127.0.0.1:8080"
    llm_model: str = "qwen2.5-1.5b-instruct-q4_k_m.gguf"
    llm_timeout_seconds: float = 45.0
    stt_model: str = "small"
    stt_timeout_seconds: float = 45.0
    tts_voice_dir: str = ".models/voices"
    tts_timeout_seconds: float = 30.0
    dialog_api_key: str | None = None

    @property
    def infrastructure_configured(self) -> bool:
        return all(
            (
                self.database_url,
                self.redis_url,
                self.minio_endpoint,
                self.minio_access_key,
                self.minio_secret_key,
            )
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
