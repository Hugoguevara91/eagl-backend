import os
from functools import lru_cache
from pathlib import Path
from typing import List

from dotenv import load_dotenv

load_dotenv()


class Settings:
    def __init__(self) -> None:
        base_dir = Path(__file__).resolve().parent.parent.parent
        self.APP_NAME: str = os.getenv("APP_NAME", "EAGL API")
        self.SECRET_KEY: str = os.getenv("SECRET_KEY", "dev-secret-change-me")
        self.ACCESS_TOKEN_EXPIRE_HOURS: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_HOURS", "8"))
        self.ALGORITHM: str = os.getenv("ALGORITHM", "HS256")
        self.SQLALCHEMY_DATABASE_URI: str = os.getenv(
            "SQLALCHEMY_DATABASE_URI",
            f"sqlite:///{(base_dir / 'eagl.db').as_posix()}",
        )
        self.ENV: str = os.getenv("ENV", "development")

        default_cors = [
            "http://localhost",
            "http://localhost:3000",
            "http://localhost:5173",
            "http://localhost:5174",
            "http://127.0.0.1",
            "http://127.0.0.1:3000",
            "http://127.0.0.1:5173",
            "http://127.0.0.1:5174",
            "https://eagl.com.br",
            "https://app.eagl.com.br",
            "https://console.eagl.com.br",
            "https://eagl-console.web.app",
            "https://eagl-landing.web.app",
            "https://eagl-bd262.web.app",
        ]
        cors_origins = os.getenv("BACKEND_CORS_ORIGINS")
        self.BACKEND_CORS_ORIGINS: List[str] = (
            [origin.strip() for origin in cors_origins.split(",") if origin.strip()]
            if cors_origins
            else default_cors
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
