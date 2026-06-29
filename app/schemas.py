from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


ScanStatus = Literal["UPLOADED", "PROCESSING", "NEEDS_REVIEW", "COMPLETED", "FAILED"]


class ElementDetected(BaseModel):
    row_number: int | None = None
    element_tag: str
    element_name: str
    category: str | None = None
    findings: str | None = None
    source_line: str | None = None

    @field_validator("category")
    @classmethod
    def validate_category(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return None
        normalized = value.upper().strip()
        if normalized not in {"A", "B", "C", "D", "E"}:
            raise ValueError("category harus A, B, C, D, atau E")
        return normalized


class InspectionMetadata(BaseModel):
    form_no: str | None = None
    revision: str | None = None
    equipment_id: str | None = None
    equipment_name: str | None = None
    location: str | None = None
    equipment_type: str | None = None
    inspection_date: date | None = None
    inspector: str | None = None
    method: str | None = None
    status: str | None = None


class StructuredInspection(BaseModel):
    metadata: InspectionMetadata
    elements: list[ElementDetected] = Field(default_factory=list)
    overall_condition: str | None = None
    recommendation: str | None = None
    warnings: list[str] = Field(default_factory=list)


class ScanCreateResponse(BaseModel):
    job_id: int
    filename: str
    status: ScanStatus


class ScanJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    original_filename: str
    content_type: str | None
    file_size: int
    status: ScanStatus
    selected_engine: str | None
    tesseract_confidence: float | None
    paddle_confidence: float | None
    estimated_reliability: float | None
    error_message: str | None
    inspection_id: int | None
    created_at: datetime
    completed_at: datetime | None


class ScanResultResponse(BaseModel):
    job: ScanJobResponse
    raw_text: str | None
    structured: StructuredInspection | None
    candidates: list[dict[str, Any]] = Field(default_factory=list)


class InspectionListItem(BaseModel):
    id: int
    equipment_tag: str
    equipment_name: str | None
    inspector: str
    inspection_date: date | None
    method: str | None
    overall_condition: str | None
    status: str | None


class InspectionDetail(BaseModel):
    inspection: dict[str, Any]
    equipment: dict[str, Any]
    inspector: dict[str, Any]
    elements: list[dict[str, Any]]
