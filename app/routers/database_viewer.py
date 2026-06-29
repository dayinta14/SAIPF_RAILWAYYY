from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from app.database import get_db


router = APIRouter(prefix="/api/database", tags=["Database Viewer"])

ALLOWED_TABLES = {
    "scan_job",
    "equipment",
    "inspector",
    "inspection",
    "element",
    "colour",
    "element_inspection",
}


@router.get("/tables")
def list_tables(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    inspector = inspect(db.get_bind())
    output: list[dict[str, Any]] = []
    for table_name in sorted(name for name in inspector.get_table_names() if name in ALLOWED_TABLES):
        output.append(
            {
                "table": table_name,
                "columns": [column["name"] for column in inspector.get_columns(table_name)],
            }
        )
    return output


@router.get("/tables/{table_name}")
def read_table(
    table_name: str,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    if table_name not in ALLOWED_TABLES:
        raise HTTPException(status_code=404, detail="Tabel tidak tersedia.")
    limit = max(1, min(limit, 500))
    offset = max(0, offset)
    count = db.execute(text(f'SELECT COUNT(*) FROM "{table_name}"')).scalar_one()
    rows = db.execute(
        text(f'SELECT * FROM "{table_name}" ORDER BY id DESC LIMIT :limit OFFSET :offset'),
        {"limit": limit, "offset": offset},
    ).mappings().all()
    return {"table": table_name, "total": count, "items": [dict(row) for row in rows]}
