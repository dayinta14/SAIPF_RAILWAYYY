from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Equipment, Inspection, Inspector
from app.repositories import inspection_detail
from app.schemas import InspectionDetail, InspectionListItem


router = APIRouter(prefix="/api/inspections", tags=["Inspections"])


@router.get("", response_model=list[InspectionListItem])
def list_inspections(limit: int = 100, db: Session = Depends(get_db)) -> list[InspectionListItem]:
    limit = max(1, min(limit, 500))
    rows = db.execute(
        select(Inspection, Equipment, Inspector)
        .join(Equipment, Equipment.id == Inspection.equipment_id)
        .join(Inspector, Inspector.id == Inspection.inspector_id)
        .order_by(Inspection.id.desc())
        .limit(limit)
    ).all()
    return [
        InspectionListItem(
            id=inspection.id,
            equipment_tag=equipment.tag_number,
            equipment_name=equipment.equipment_description,
            inspector=inspector.display_name or inspector.username,
            inspection_date=inspection.inspection_date,
            method=inspection.inspection_method,
            overall_condition=inspection.overall_condition,
            status=inspection.status,
        )
        for inspection, equipment, inspector in rows
    ]


@router.get("/{inspection_id}", response_model=InspectionDetail)
def get_inspection(inspection_id: int, db: Session = Depends(get_db)) -> InspectionDetail:
    result = inspection_detail(db, inspection_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Inspection tidak ditemukan.")
    return InspectionDetail.model_validate(result)
