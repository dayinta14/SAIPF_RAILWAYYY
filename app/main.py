from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.database import Base, SessionLocal, engine
from app.repositories import seed_colours
from app.routers import dashboard, database_viewer, inspections, scans
from app.webgl_integration import register_webgl


# Folder frontend berada sejajar dengan folder app
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings.ensure_directories()
    Base.metadata.create_all(bind=engine)

    with SessionLocal() as session:
        seed_colours(session)

    yield


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=(
        "Backend SAIPF untuk upload dokumen inspeksi, "
        "OCR Tesseract/PaddleOCR, ekstraksi data, "
        "verifikasi hasil, dashboard historis, "
        "visualisasi WebGL, dan penyimpanan SQLite."
    ),
    lifespan=lifespan,
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# API routers — wajib sebelum app.mount("/")
app.include_router(scans.router)
app.include_router(inspections.router)
app.include_router(database_viewer.router)
app.include_router(dashboard.router)


@app.get("/health", tags=["System"])
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/system", tags=["System"])
def system_information() -> dict[str, str]:
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "docs": "/docs",
        "health": "/health",
        "dashboard": "/dashboard.html",
        "dashboard_api": "/api/dashboard",
    }


# WebGL harus didaftarkan sebelum mount frontend
register_webgl(app)


# Harus paling bawah karena "/" menjadi fallback frontend
app.mount(
    "/",
    StaticFiles(directory=str(FRONTEND_DIR), html=True),
    name="frontend",
)
