"""TRACE-X Settings and Environment Configuration."""
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    PROJECT_NAME: str = "TRACE-X Fraud Tracing MVP"
    VERSION: str = "1.0.0-hackathon-mvp"
    API_V1_STR: str = "/api/v1"
    
    # Database URL: defaults to SQLite for zero-config portable hackathon run,
    # or PostgreSQL if configured in .env
    DATABASE_URL: str = "sqlite:///./tracex_mvp.db"
    
    # JWT & Auth
    SECRET_KEY: str = "tracex-hackathon-super-secret-key-2026-v1"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # 24 hours for demo
    ALGORITHM: str = "HS256"

    # Synthetic demo flag
    IS_SYNTHETIC_DEMO: bool = True

    class Config:
        env_file = ".env"
        extra = "allow"


settings = Settings()
