from __future__ import annotations

import os
import re
import sqlite3
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

router = APIRouter(tags=["WebGL Visualization"])

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = Path(os.getenv("SAIPF_DB_PATH", PROJECT_ROOT / "data" / "SAIPF.db"))
MODEL_DIR = PROJECT_ROOT / "static" / "models"

CATEGORY_STYLE: dict[str, dict[str, Any]] = {
    "A": {"label": "Sangat Baik", "color_hex": "#22C55E", "opacity": 1.0},
    "B": {"label": "Baik", "color_hex": "#86EFAC", "opacity": 1.0},
    "C": {"label": "Perlu Perhatian", "color_hex": "#FACC15", "opacity": 1.0},
    "D": {"label": "Perlu Perbaikan", "color_hex": "#F97316", "opacity": 1.0},
    "E": {"label": "Kritis / Rusak", "color_hex": "#EF4444", "opacity": 1.0},
    "UNINSPECTED": {"label": "Belum Diinspeksi", "color_hex": "#D1D5DB", "opacity": 0.18},
}


class MappingUpdate(BaseModel):
    model_key: str = Field(min_length=1, max_length=255)
    node_name: str | None = Field(default=None, max_length=255)
    sketchup_persistent_id: str | None = Field(default=None, max_length=100)


class AssetCreate(BaseModel):
    equipment_id: int
    model_name: str = Field(min_length=1, max_length=255)
    model_url: str = Field(min_length=1, max_length=500)
    version: str | None = Field(default=None, max_length=50)


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def ensure_visualization_schema() -> None:
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    with _connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS model_asset (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                equipment_id INTEGER NOT NULL,
                model_name TEXT NOT NULL,
                model_url TEXT NOT NULL,
                version TEXT,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (equipment_id) REFERENCES equipment(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_model_asset_equipment
                ON model_asset(equipment_id, is_active);

            CREATE TABLE IF NOT EXISTS element_model_map (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                model_asset_id INTEGER NOT NULL,
                element_id INTEGER NOT NULL,
                model_key TEXT NOT NULL,
                node_name TEXT,
                sketchup_persistent_id TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (model_asset_id) REFERENCES model_asset(id) ON DELETE CASCADE,
                FOREIGN KEY (element_id) REFERENCES element(id) ON DELETE CASCADE,
                UNIQUE (model_asset_id, element_id),
                UNIQUE (model_asset_id, model_key)
            );

            CREATE INDEX IF NOT EXISTS idx_element_model_map_element
                ON element_model_map(element_id);
            """
        )


def _safe_filename(filename: str) -> str:
    stem = Path(filename).stem
    suffix = Path(filename).suffix.lower()
    clean_stem = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("._") or "model"
    return f"{clean_stem}{suffix}"


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table_name,)
    ).fetchone()
    return row is not None


def _require_core_tables(conn: sqlite3.Connection) -> None:
    required = {"inspection", "equipment", "element", "element_inspection"}
    missing = sorted(name for name in required if not _table_exists(conn, name))
    if missing:
        raise HTTPException(
            status_code=500,
            detail=(
                "Tabel inti SAIPF belum ditemukan: " + ", ".join(missing) + ". "
                "Pastikan memakai database data/SAIPF.db dari backend SAIPF."
            ),
        )


def _get_inspection(conn: sqlite3.Connection, inspection_id: int) -> sqlite3.Row:
    row = conn.execute(
        """
        SELECT
            i.id,
            i.equipment_id,
            i.inspection_date,
            i.inspection_method,
            i.overall_condition,
            i.recommendation,
            i.status,
            e.tag_number AS equipment_tag,
            e.equipment_description AS equipment_name,
            e.equipment_type,
            e.plant_id,
            e.section
        FROM inspection AS i
        JOIN equipment AS e ON e.id = i.equipment_id
        WHERE i.id = ?
        """,
        (inspection_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Inspection tidak ditemukan")
    return row


def _active_asset(conn: sqlite3.Connection, equipment_id: int) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT id, equipment_id, model_name, model_url, version, is_active, created_at
        FROM model_asset
        WHERE equipment_id = ? AND is_active = 1
        ORDER BY id DESC
        LIMIT 1
        """,
        (equipment_id,),
    ).fetchone()


@router.get("/api/inspections/{inspection_id}/visualization")
def inspection_visualization(inspection_id: int) -> dict[str, Any]:
    """Menggabungkan hasil inspeksi, mapping elemen, dan model GLB aktif."""
    ensure_visualization_schema()
    with _connect() as conn:
        _require_core_tables(conn)
        inspection = _get_inspection(conn, inspection_id)
        asset = _active_asset(conn, int(inspection["equipment_id"]))

        asset_id = int(asset["id"]) if asset else None
        rows = conn.execute(
            """
            SELECT
                e.id AS element_id,
                e.element_tag,
                e.element_name,
                ei.category,
                ei.findings,
                emm.model_key,
                emm.node_name,
                emm.sketchup_persistent_id
            FROM element_inspection AS ei
            JOIN element AS e ON e.id = ei.element_id
            LEFT JOIN element_model_map AS emm
                ON emm.element_id = e.id
               AND emm.model_asset_id = ?
            WHERE ei.inspection_id = ?
            ORDER BY e.element_tag
            """,
            (asset_id if asset_id is not None else -1, inspection_id),
        ).fetchall()

        parts: list[dict[str, Any]] = []
        unmapped: list[dict[str, Any]] = []
        for row in rows:
            category = (row["category"] or "UNINSPECTED").upper()
            style = CATEGORY_STYLE.get(category, CATEGORY_STYLE["UNINSPECTED"])
            item = {
                "element_id": row["element_id"],
                "element_tag": row["element_tag"],
                "element_name": row["element_name"],
                "model_key": row["model_key"],
                "node_name": row["node_name"],
                "sketchup_persistent_id": row["sketchup_persistent_id"],
                "category": category,
                "category_label": style["label"],
                "color_hex": style["color_hex"],
                "opacity": style["opacity"],
                "findings": row["findings"],
            }
            parts.append(item)
            if not row["model_key"]:
                unmapped.append(
                    {
                        "element_id": row["element_id"],
                        "element_tag": row["element_tag"],
                        "element_name": row["element_name"],
                        "reason": "Belum dipetakan ke node pada model GLB",
                    }
                )

        return {
            "inspection_id": inspection["id"],
            "inspection_date": inspection["inspection_date"],
            "inspection_method": inspection["inspection_method"],
            "overall_condition": inspection["overall_condition"],
            "recommendation": inspection["recommendation"],
            "status": inspection["status"],
            "equipment": {
                "id": inspection["equipment_id"],
                "tag_number": inspection["equipment_tag"],
                "equipment_name": inspection["equipment_name"],
                "equipment_type": inspection["equipment_type"],
                "plant_id": inspection["plant_id"],
                "section": inspection["section"],
            },
            "asset": dict(asset) if asset else None,
            "model_url": asset["model_url"] if asset else None,
            "parts": parts,
            "unmapped_elements": unmapped,
            "category_style": CATEGORY_STYLE,
        }


@router.get("/api/visualization/assets")
def list_assets(equipment_id: int | None = None) -> list[dict[str, Any]]:
    ensure_visualization_schema()
    with _connect() as conn:
        if equipment_id is None:
            rows = conn.execute(
                "SELECT * FROM model_asset ORDER BY id DESC"
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM model_asset WHERE equipment_id=? ORDER BY id DESC",
                (equipment_id,),
            ).fetchall()
        return [dict(row) for row in rows]


@router.post("/api/visualization/assets")
def create_asset(payload: AssetCreate) -> dict[str, Any]:
    ensure_visualization_schema()
    with _connect() as conn:
        equipment = conn.execute(
            "SELECT id FROM equipment WHERE id=?", (payload.equipment_id,)
        ).fetchone()
        if equipment is None:
            raise HTTPException(status_code=404, detail="Equipment tidak ditemukan")

        conn.execute(
            "UPDATE model_asset SET is_active=0 WHERE equipment_id=?",
            (payload.equipment_id,),
        )
        cursor = conn.execute(
            """
            INSERT INTO model_asset(equipment_id, model_name, model_url, version, is_active)
            VALUES (?, ?, ?, ?, 1)
            """,
            (
                payload.equipment_id,
                payload.model_name,
                payload.model_url,
                payload.version,
            ),
        )
        asset_id = int(cursor.lastrowid)
        row = conn.execute("SELECT * FROM model_asset WHERE id=?", (asset_id,)).fetchone()
        return dict(row)


@router.post("/api/visualization/assets/upload")
async def upload_asset(
    equipment_id: int = Form(...),
    model_file: UploadFile = File(...),
    version: str | None = Form(default=None),
) -> dict[str, Any]:
    """Upload file .glb/.gltf dan menjadikannya model aktif equipment."""
    ensure_visualization_schema()
    original_name = model_file.filename or "model.glb"
    suffix = Path(original_name).suffix.lower()
    if suffix not in {".glb", ".gltf"}:
        raise HTTPException(
            status_code=400,
            detail="Format model harus .glb atau .gltf. File .skp diekspor dahulu dari SketchUp.",
        )

    with _connect() as conn:
        equipment = conn.execute(
            "SELECT id, tag_number FROM equipment WHERE id=?", (equipment_id,)
        ).fetchone()
        if equipment is None:
            raise HTTPException(status_code=404, detail="Equipment tidak ditemukan")

        MODEL_DIR.mkdir(parents=True, exist_ok=True)
        safe_name = _safe_filename(original_name)
        target_name = f"equipment_{equipment_id}_{safe_name}"
        target = MODEL_DIR / target_name

        content = await model_file.read()
        if not content:
            raise HTTPException(status_code=400, detail="File model kosong")
        target.write_bytes(content)

        model_url = f"/models/{target_name}"
        conn.execute(
            "UPDATE model_asset SET is_active=0 WHERE equipment_id=?", (equipment_id,)
        )
        cursor = conn.execute(
            """
            INSERT INTO model_asset(equipment_id, model_name, model_url, version, is_active)
            VALUES (?, ?, ?, ?, 1)
            """,
            (equipment_id, original_name, model_url, version),
        )
        asset_id = int(cursor.lastrowid)
        row = conn.execute("SELECT * FROM model_asset WHERE id=?", (asset_id,)).fetchone()
        return dict(row)


@router.get("/api/visualization/assets/{asset_id}/mappings")
def list_mappings(asset_id: int) -> list[dict[str, Any]]:
    ensure_visualization_schema()
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT
                emm.id,
                emm.model_asset_id,
                emm.element_id,
                e.element_tag,
                e.element_name,
                emm.model_key,
                emm.node_name,
                emm.sketchup_persistent_id,
                emm.created_at,
                emm.updated_at
            FROM element_model_map AS emm
            JOIN element AS e ON e.id = emm.element_id
            WHERE emm.model_asset_id = ?
            ORDER BY e.element_tag
            """,
            (asset_id,),
        ).fetchall()
        return [dict(row) for row in rows]


@router.put("/api/visualization/assets/{asset_id}/mappings/{element_id}")
def upsert_mapping(
    asset_id: int,
    element_id: int,
    payload: MappingUpdate,
) -> dict[str, Any]:
    ensure_visualization_schema()
    model_key = payload.model_key.strip()
    node_name = (payload.node_name or model_key).strip()
    with _connect() as conn:
        asset = conn.execute(
            "SELECT id, equipment_id FROM model_asset WHERE id=?", (asset_id,)
        ).fetchone()
        if asset is None:
            raise HTTPException(status_code=404, detail="Model asset tidak ditemukan")

        element = conn.execute(
            "SELECT id, element_tag, element_name FROM element WHERE id=?", (element_id,)
        ).fetchone()
        if element is None:
            raise HTTPException(status_code=404, detail="Elemen tidak ditemukan")

        conflict = conn.execute(
            """
            SELECT element_id FROM element_model_map
            WHERE model_asset_id=? AND model_key=? AND element_id<>?
            """,
            (asset_id, model_key, element_id),
        ).fetchone()
        if conflict:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Node/model_key '{model_key}' sudah dipakai oleh element_id "
                    f"{conflict['element_id']}."
                ),
            )

        conn.execute(
            """
            INSERT INTO element_model_map(
                model_asset_id,
                element_id,
                model_key,
                node_name,
                sketchup_persistent_id
            )
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(model_asset_id, element_id)
            DO UPDATE SET
                model_key=excluded.model_key,
                node_name=excluded.node_name,
                sketchup_persistent_id=excluded.sketchup_persistent_id,
                updated_at=CURRENT_TIMESTAMP
            """,
            (
                asset_id,
                element_id,
                model_key,
                node_name,
                payload.sketchup_persistent_id,
            ),
        )
        row = conn.execute(
            """
            SELECT
                emm.*,
                e.element_tag,
                e.element_name
            FROM element_model_map AS emm
            JOIN element AS e ON e.id=emm.element_id
            WHERE emm.model_asset_id=? AND emm.element_id=?
            """,
            (asset_id, element_id),
        ).fetchone()
        return dict(row)


@router.delete("/api/visualization/assets/{asset_id}/mappings/{element_id}")
def delete_mapping(asset_id: int, element_id: int) -> dict[str, Any]:
    ensure_visualization_schema()
    with _connect() as conn:
        cursor = conn.execute(
            "DELETE FROM element_model_map WHERE model_asset_id=? AND element_id=?",
            (asset_id, element_id),
        )
        return {"deleted": cursor.rowcount > 0}
