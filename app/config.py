from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    app_name: str = os.getenv("APP_NAME", "SAIPF OCR Backend")
    app_version: str = os.getenv("APP_VERSION", "1.0.0")
    debug: bool = os.getenv("DEBUG", "false").lower() == "true"

    data_dir: Path = Path(os.getenv("DATA_DIR", "data"))
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./data/SAIPF.db")
    max_upload_mb: int = int(os.getenv("MAX_UPLOAD_MB", "20"))
    render_dpi: int = int(os.getenv("RENDER_DPI", "300"))

    tesseract_lang: str = os.getenv("TESSERACT_LANG", "ind+eng")
    tesseract_timeout_seconds: int = int(os.getenv("TESSERACT_TIMEOUT_SECONDS", "90"))
    paddle_lang: str = os.getenv("PADDLE_LANG", "id")
    paddle_device: str = os.getenv("PADDLE_DEVICE", "cpu")
    enable_paddleocr: bool = os.getenv("ENABLE_PADDLEOCR", "true").lower() == "true"

    cors_origins: tuple[str, ...] = tuple(
        origin.strip()
        for origin in os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:5173").split(",")
        if origin.strip()
    )

    @property
    def upload_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def processed_dir(self) -> Path:
        return self.data_dir / "processed"

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    def ensure_directories(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self.processed_dir.mkdir(parents=True, exist_ok=True)


settings = Settings()
