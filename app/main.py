```python
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


# Folder frontend berada sejajar dengan folder app:
#
# SAIPF_RAILWAYYY/
# ├── app/
# │   └── main.py
# └── frontend/
#     ├── index.html
#     └── dashboard.html
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """
    Menjalankan proses inisialisasi ketika aplikasi mulai.

    Proses yang dilakukan:
    1. Membuat folder upload dan hasil pemrosesan.
    2. Membuat seluruh tabel database jika belum tersedia.
    3. Mengisi data warna kategori A-E.
    """
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


# ============================================================
# CORS
# ============================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# API ROUTERS
# Semua router harus didaftarkan sebelum frontend di-mount.
# ============================================================

# API upload, proses OCR, polling job, dan konfirmasi hasil
app.include_router(scans.router)

# API data inspeksi dan elemen hasil inspeksi
app.include_router(inspections.router)

# API untuk melihat data database
app.include_router(database_viewer.router)

# API statistik dan data dashboard historis
app.include_router(dashboard.router)


# ============================================================
# SYSTEM ENDPOINTS
# ============================================================

@app.get("/health", tags=["System"])
def health() -> dict[str, str]:
    """
    Health check untuk Railway.
    """
    return {
        "status": "ok",
    }


@app.get("/api/system", tags=["System"])
def system_information() -> dict[str, str]:
    """
    Informasi dasar aplikasi.
    """
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "docs": "/docs",
        "health": "/health",
        "dashboard": "/dashboard.html",
        "dashboard_api": "/api/dashboard",
    }


# ============================================================
# WEBGL
# WebGL harus didaftarkan sebelum frontend dengan path "/".
# ============================================================

register_webgl(app)


# ============================================================
# FRONTEND
# Mount "/" wajib berada paling bawah karena menjadi fallback
# untuk seluruh file HTML, CSS, JavaScript, dan aset frontend.
# ============================================================

app.mount(
    "/",
    StaticFiles(
        directory=str(FRONTEND_DIR),
        html=True,
    ),
    name="frontend",
)
```
