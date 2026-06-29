from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.models import Equipment, Inspection, ScanJob


router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])


def _normalize_status(value: str | None) -> str:
    return str(value or "").strip().replace(" ", "_").upper()


def _date_in_range(
    value: date | datetime | None,
    date_from: date | None,
    date_to: date | None,
) -> bool:
    if value is None:
        return False

    current = value.date() if isinstance(value, datetime) else value

    if date_from and current < date_from:
        return False

    if date_to and current > date_to:
        return False

    return True


def _inspection_matches(
    inspection: Inspection,
    *,
    date_from: date | None,
    date_to: date | None,
    plant_id: str | None,
    section: str | None,
    equipment_type: str | None,
    overall_condition: str | None,
    status: str | None,
) -> bool:
    equipment = inspection.equipment

    if date_from or date_to:
        if not _date_in_range(inspection.inspection_date, date_from, date_to):
            return False

    if plant_id and (equipment.plant_id or "") != plant_id:
        return False

    if section and (equipment.section or "") != section:
        return False

    if equipment_type and (equipment.equipment_type or "") != equipment_type:
        return False

    if overall_condition and (inspection.overall_condition or "").upper() != overall_condition.upper():
        return False

    if status and _normalize_status(inspection.status) != _normalize_status(status):
        return False

    return True


@router.get("")
def dashboard_data(
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    plant_id: str | None = Query(default=None),
    section: str | None = Query(default=None),
    equipment_type: str | None = Query(default=None),
    overall_condition: str | None = Query(default=None),
    status: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    inspection_query = (
        select(Inspection)
        .options(
            selectinload(Inspection.equipment),
            selectinload(Inspection.inspector),
            selectinload(Inspection.element_inspections),
        )
        .order_by(Inspection.inspection_date.desc(), Inspection.id.desc())
    )

    all_inspections = list(db.scalars(inspection_query).unique())

    inspections = [
        inspection
        for inspection in all_inspections
        if _inspection_matches(
            inspection,
            date_from=date_from,
            date_to=date_to,
            plant_id=plant_id,
            section=section,
            equipment_type=equipment_type,
            overall_condition=overall_condition,
            status=status,
        )
    ]

    scan_query = select(ScanJob).order_by(ScanJob.created_at.desc(), ScanJob.id.desc())
    all_scans = list(db.scalars(scan_query))

    scans = [
        scan
        for scan in all_scans
        if not (date_from or date_to)
        or _date_in_range(scan.created_at, date_from, date_to)
    ]

    equipment_ids = {inspection.equipment_id for inspection in inspections}
    critical_equipment_ids = {
        inspection.equipment_id
        for inspection in inspections
        if (inspection.overall_condition or "").upper() == "E"
    }

    today = date.today()
    inspections_this_month = sum(
        1
        for inspection in inspections
        if inspection.inspection_date
        and inspection.inspection_date.year == today.year
        and inspection.inspection_date.month == today.month
    )

    critical_findings = 0
    element_category_distribution = Counter({key: 0 for key in "ABCDE"})
    critical_rows: list[dict[str, Any]] = []

    for inspection in inspections:
        finding_count = 0

        for result in inspection.element_inspections:
            category = (result.category or "").upper()

            if category in element_category_distribution:
                element_category_distribution[category] += 1

            if category == "E":
                finding_count += 1
                critical_findings += 1

        if (
            (inspection.overall_condition or "").upper() == "E"
            or finding_count > 0
        ):
            critical_rows.append(
                {
                    "inspection_id": inspection.id,
                    "tag_number": inspection.equipment.tag_number,
                    "equipment_name": inspection.equipment.equipment_description,
                    "equipment_type": inspection.equipment.equipment_type,
                    "plant_id": inspection.equipment.plant_id,
                    "section": inspection.equipment.section,
                    "overall_condition": inspection.overall_condition,
                    "critical_findings": finding_count,
                    "inspection_date": (
                        inspection.inspection_date.isoformat()
                        if inspection.inspection_date
                        else None
                    ),
                    "status": inspection.status,
                    "recommendation": inspection.recommendation,
                }
            )

    critical_rows.sort(
        key=lambda row: (
            row["critical_findings"],
            row["inspection_date"] or "",
        ),
        reverse=True,
    )

    condition_distribution = Counter({key: 0 for key in "ABCDE"})
    for inspection in inspections:
        category = (inspection.overall_condition or "").upper()
        if category in condition_distribution:
            condition_distribution[category] += 1

    monthly_trend_map: dict[str, int] = defaultdict(int)
    for inspection in inspections:
        if inspection.inspection_date:
            month_key = inspection.inspection_date.strftime("%Y-%m")
            monthly_trend_map[month_key] += 1

    monthly_trend = [
        {"month": month, "total": monthly_trend_map[month]}
        for month in sorted(monthly_trend_map)
    ]

    scan_status_distribution = Counter(
        _normalize_status(scan.status) or "UNKNOWN"
        for scan in scans
    )

    engine_distribution = Counter(
        scan.selected_engine or "Belum dipilih"
        for scan in scans
    )

    reliability_values = [
        float(scan.estimated_reliability)
        for scan in scans
        if scan.estimated_reliability is not None
    ]

    average_reliability = (
        sum(reliability_values) / len(reliability_values)
        if reliability_values
        else 0.0
    )

    recent_inspections = [
        {
            "id": inspection.id,
            "equipment_tag": inspection.equipment.tag_number,
            "equipment_name": inspection.equipment.equipment_description,
            "equipment_type": inspection.equipment.equipment_type,
            "plant_id": inspection.equipment.plant_id,
            "section": inspection.equipment.section,
            "inspector": (
                inspection.inspector.display_name
                or inspection.inspector.username
            ),
            "inspection_date": (
                inspection.inspection_date.isoformat()
                if inspection.inspection_date
                else None
            ),
            "method": inspection.inspection_method,
            "overall_condition": inspection.overall_condition,
            "status": inspection.status,
        }
        for inspection in inspections[:15]
    ]

    recent_scans = [
        {
            "id": scan.id,
            "original_filename": scan.original_filename,
            "status": scan.status,
            "selected_engine": scan.selected_engine,
            "estimated_reliability": scan.estimated_reliability,
            "inspection_id": scan.inspection_id,
            "created_at": scan.created_at.isoformat(),
            "completed_at": (
                scan.completed_at.isoformat()
                if scan.completed_at
                else None
            ),
            "error_message": scan.error_message,
        }
        for scan in scans[:10]
    ]

    unique_plants = sorted(
        {
            inspection.equipment.plant_id
            for inspection in all_inspections
            if inspection.equipment.plant_id
        }
    )

    unique_sections = sorted(
        {
            inspection.equipment.section
            for inspection in all_inspections
            if inspection.equipment.section
        }
    )

    unique_types = sorted(
        {
            inspection.equipment.equipment_type
            for inspection in all_inspections
            if inspection.equipment.equipment_type
        }
    )

    unique_statuses = sorted(
        {
            _normalize_status(inspection.status)
            for inspection in all_inspections
            if inspection.status
        }
    )

    return {
        "filters": {
            "date_from": date_from.isoformat() if date_from else None,
            "date_to": date_to.isoformat() if date_to else None,
            "plant_id": plant_id,
            "section": section,
            "equipment_type": equipment_type,
            "overall_condition": overall_condition,
            "status": status,
        },
        "filter_options": {
            "plants": unique_plants,
            "sections": unique_sections,
            "equipment_types": unique_types,
            "statuses": unique_statuses,
        },
        "summary": {
            "total_scans": len(scans),
            "total_inspections": len(inspections),
            "total_equipment": len(equipment_ids),
            "critical_equipment": len(critical_equipment_ids),
            "critical_findings": critical_findings,
            "pending_review": sum(
                1
                for scan in scans
                if _normalize_status(scan.status) == "NEEDS_REVIEW"
            ),
            "failed_scans": sum(
                1
                for scan in scans
                if _normalize_status(scan.status) == "FAILED"
            ),
            "inspections_this_month": inspections_this_month,
            "average_reliability": average_reliability,
        },
        "inspection_condition_distribution": dict(condition_distribution),
        "element_category_distribution": dict(element_category_distribution),
        "monthly_inspection_trend": monthly_trend,
        "scan_status_distribution": dict(scan_status_distribution),
        "engine_distribution": dict(engine_distribution),
        "critical_equipment": critical_rows[:20],
        "recent_inspections": recent_inspections,
        "recent_scans": recent_scans,
    }
