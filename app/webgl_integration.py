from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.routers.visualization import ensure_visualization_schema, router


def register_webgl(app: FastAPI) -> None:
    """Mendaftarkan API visualisasi dan halaman Three.js ke aplikasi FastAPI."""
    project_root = Path(__file__).resolve().parents[1]
    viewer_dir = project_root / "webgl"
    model_dir = project_root / "static" / "models"

    viewer_dir.mkdir(parents=True, exist_ok=True)
    model_dir.mkdir(parents=True, exist_ok=True)
    ensure_visualization_schema()

    app.include_router(router)
    app.mount("/models", StaticFiles(directory=str(model_dir)), name="saipf-models")
    app.mount("/viewer", StaticFiles(directory=str(viewer_dir), html=True), name="saipf-viewer")
