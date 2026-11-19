from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import List

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


class Settings:
    def __init__(self) -> None:
        self.app_name: str = "AI E-Commerce Intelligence System"
        default_db = f"sqlite:///{(BASE_DIR / 'ecommerce_intelligence.db').as_posix()}"
        self.database_url: str = os.getenv("DATABASE_URL", default_db)
        self.secret_key: str = os.getenv(
            "APP_SECRET_KEY",
            "local-dev-secret-key-please-override-in-env-file-32chars",
        )
        self.access_token_expire_minutes: int = int(
            os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "720")
        )
        upload_rel = os.getenv("UPLOAD_DIR", "storage/uploads")
        upload_path = Path(upload_rel)
        if not upload_path.is_absolute():
            upload_path = BASE_DIR / upload_path
        self.upload_dir: Path = upload_path
        self.upload_dir.mkdir(parents=True, exist_ok=True)

        raw_origins = os.getenv(
            "CORS_ORIGINS",
            "http://localhost:8000,http://127.0.0.1:8000,http://localhost:3000,http://127.0.0.1:3000",
        )
        self.cors_origins: List[str] = [
            o.strip() for o in raw_origins.split(",") if o.strip()
        ]
        self.log_level: str = os.getenv("LOG_LEVEL", "INFO").upper()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
