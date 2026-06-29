from __future__ import annotations

import json
import re
import unicodedata
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import Colour, Element, ElementInspection, Equipment, Inspection, Inspector, ScanJob
from app.schemas import StructuredInspection


COLOURS = {
    "A": "Hijau",
    "B": "Hijau Muda",
    "C": "Kuning",
    "D": "Oranye",
    "E": "Merah",
}


def seed_colours(session: Session) -> None:
    for category, colour_name in COLOURS.items():
        colour = session.scalar(select(Colour).where(Colour.category == category))
        if colour is None:
            session.add(Colour(category=category, warna=colour_name))
        else:
            colour.warna = colour_name
    session.commit()


def slugify(value: str | None) -> str:
    text = unicodedata.normalize("NFKD", value or "unknown inspector")
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = re.sub(r"[^a-z0-9]+", ".", text.casefold()).strip(".")
    return text or "unknown.inspector"


def split_location(value: str | None) -> tuple[str | None, str | None]:
    if not value:
        return None, None
    if " - " in value:
        plant, section = value.split(" - ", 1)
        return plant.strip(), section.strip()
    return value.strip(), None


def persist_confirmed_scan(session: Session, job: ScanJob, structured: StructuredInspection) -> Inspection:
    if job.inspection_id:
        existing = session.get(Inspection, job.inspection_id)
        if existing is not None:
            return existing

    metadata = structured.metadata
    if not metadata.equipment_id:
        raise ValueError("Equipment ID wajib diisi sebelum konfirmasi.")
    if not metadata.inspector:
        raise ValueError("Nama inspektor wajib diisi sebelum konfirmasi.")
    if not structured.elements:
        raise ValueError("Minimal satu elemen inspeksi diperlukan.")

    plant_id, section = split_location(metadata.location)
    equipment = session.scalar(select(Equipment).where(Equipment.tag_number == metadata.equipment_id))
    if equipment is None:
        equipment = Equipment(tag_number=metadata.equipment_id)
        session.add(equipment)
        session.flush()
    equipment.equipment_type = metadata.equipment_type or equipment.equipment_type
    equipment.equipment_description = metadata.equipment_name or equipment.equipment_description
    equipment.plant_id = plant_id or equipment.plant_id
    equipment.section = section or equipment.section
    equipment.is_active = True

    username = slugify(metadata.inspector)
    inspector = session.scalar(select(Inspector).where(Inspector.username == username))
    if inspector is None:
        inspector = Inspector(username=username, display_name=metadata.inspector, role="inspector")
        session.add(inspector)
        session.flush()
    else:
        inspector.display_name = metadata.inspector

    query = select(Inspection).where(
        Inspection.equipment_id == equipment.id,
        Inspection.inspection_date == metadata.inspection_date,
        Inspection.inspection_method == metadata.method,
    )
    inspection = session.scalar(query)
    if inspection is None:
        inspection = Inspection(
            equipment_id=equipment.id,
            inspector_id=inspector.id,
            inspection_date=metadata.inspection_date,
            inspection_method=metadata.method,
        )
        session.add(inspection)
        session.flush()

    inspection.inspector_id = inspector.id
    inspection.overall_condition = structured.overall_condition
    inspection.recommendation = structured.recommendation
    inspection.status = metadata.status
    inspection.pdf_file_path = job.file_path if job.content_type == "application/pdf" else None
    inspection.json_file_path = f"scan_job:{job.id}"

    for item in structured.elements:
        element = session.scalar(
            select(Element).where(
                Element.equipment_id == equipment.id,
                Element.element_tag == item.element_tag,
            )
        )
        if element is None:
            element = Element(
                equipment_id=equipment.id,
                element_tag=item.element_tag,
                element_name=item.element_name,
                description_element=item.element_name,
            )
            session.add(element)
            session.flush()
        else:
            element.element_name = item.element_name
            element.description_element = item.element_name

        if item.category:
            colour = session.scalar(select(Colour).where(Colour.category == item.category))
            element.colour_id = colour.id if colour else None

        result = session.scalar(
            select(ElementInspection).where(
                ElementInspection.element_id == element.id,
                ElementInspection.inspection_id == inspection.id,
            )
        )
        if result is None:
            result = ElementInspection(element_id=element.id, inspection_id=inspection.id)
            session.add(result)
        result.category = item.category
        result.findings = item.findings

    session.flush()
    job.inspection_id = inspection.id
    job.status = "COMPLETED"
    return inspection


def inspection_detail(session: Session, inspection_id: int) -> dict[str, Any] | None:
    inspection = session.scalar(
        select(Inspection)
        .options(
            selectinload(Inspection.equipment),
            selectinload(Inspection.inspector),
            selectinload(Inspection.element_inspections).selectinload(ElementInspection.element),
        )
        .where(Inspection.id == inspection_id)
    )
    if inspection is None:
        return None

    return {
        "inspection": {
            "id": inspection.id,
            "inspection_date": inspection.inspection_date,
            "inspection_method": inspection.inspection_method,
            "overall_condition": inspection.overall_condition,
            "recommendation": inspection.recommendation,
            "status": inspection.status,
        },
        "equipment": {
            "id": inspection.equipment.id,
            "tag_number": inspection.equipment.tag_number,
            "equipment_description": inspection.equipment.equipment_description,
            "equipment_type": inspection.equipment.equipment_type,
            "plant_id": inspection.equipment.plant_id,
            "section": inspection.equipment.section,
        },
        "inspector": {
            "id": inspection.inspector.id,
            "username": inspection.inspector.username,
            "display_name": inspection.inspector.display_name,
            "role": inspection.inspector.role,
        },
        "elements": [
            {
                "element_id": result.element.id,
                "element_tag": result.element.element_tag,
                "element_name": result.element.element_name,
                "category": result.category,
                "findings": result.findings,
            }
            for result in inspection.element_inspections
        ],
    }
