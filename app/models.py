from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )


class Colour(Base):
    __tablename__ = "colour"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    warna: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    category: Mapped[str] = mapped_column(String(1), unique=True, nullable=False)


class Equipment(TimestampMixin, Base):
    __tablename__ = "equipment"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tag_number: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    equipment_type: Mapped[str | None] = mapped_column(String(100))
    plant_id: Mapped[str | None] = mapped_column(String(100))
    section: Mapped[str | None] = mapped_column(String(150))
    design_pressure: Mapped[float | None] = mapped_column(Float)
    design_temperature: Mapped[float | None] = mapped_column(Float)
    material: Mapped[str | None] = mapped_column(String(100))
    year_installed: Mapped[int | None] = mapped_column(Integer)
    equipment_description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    inspections: Mapped[list["Inspection"]] = relationship(back_populates="equipment")
    elements: Mapped[list["Element"]] = relationship(back_populates="equipment")


class Inspector(Base):
    __tablename__ = "inspector"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(150), unique=True, nullable=False, index=True)
    display_name: Mapped[str | None] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(50), default="inspector", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    inspections: Mapped[list["Inspection"]] = relationship(back_populates="inspector")


class Inspection(TimestampMixin, Base):
    __tablename__ = "inspection"
    __table_args__ = (
        UniqueConstraint(
            "equipment_id",
            "inspection_date",
            "inspection_method",
            name="uq_inspection_identity",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    equipment_id: Mapped[int] = mapped_column(ForeignKey("equipment.id", ondelete="RESTRICT"), nullable=False)
    inspector_id: Mapped[int] = mapped_column(ForeignKey("inspector.id", ondelete="RESTRICT"), nullable=False)
    approval: Mapped[str | None] = mapped_column(String(100))
    inspection_date: Mapped[date | None] = mapped_column(Date)
    inspection_method: Mapped[str | None] = mapped_column(String(100))
    overall_condition: Mapped[str | None] = mapped_column(String(1))
    recommendation: Mapped[str | None] = mapped_column(Text)
    next_inspection_date: Mapped[date | None] = mapped_column(Date)
    pdf_file_path: Mapped[str | None] = mapped_column(Text)
    json_file_path: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str | None] = mapped_column(String(80))

    equipment: Mapped[Equipment] = relationship(back_populates="inspections")
    inspector: Mapped[Inspector] = relationship(back_populates="inspections")
    element_inspections: Mapped[list["ElementInspection"]] = relationship(
        back_populates="inspection",
        cascade="all, delete-orphan",
    )


class Element(TimestampMixin, Base):
    __tablename__ = "element"
    __table_args__ = (
        UniqueConstraint("equipment_id", "element_tag", name="uq_element_equipment_tag"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    equipment_id: Mapped[int] = mapped_column(ForeignKey("equipment.id", ondelete="CASCADE"), nullable=False)
    colour_id: Mapped[int | None] = mapped_column(ForeignKey("colour.id", ondelete="SET NULL"))
    element_class: Mapped[str | None] = mapped_column(String(100))
    element_name: Mapped[str] = mapped_column(String(250), nullable=False)
    element_tag: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    model_file_name: Mapped[str | None] = mapped_column(String(255))
    description_element: Mapped[str | None] = mapped_column(Text)

    equipment: Mapped[Equipment] = relationship(back_populates="elements")
    colour: Mapped[Colour | None] = relationship()
    inspection_results: Mapped[list["ElementInspection"]] = relationship(
        back_populates="element",
        cascade="all, delete-orphan",
    )


class ElementInspection(Base):
    __tablename__ = "element_inspection"
    __table_args__ = (
        UniqueConstraint("element_id", "inspection_id", name="uq_element_inspection"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    element_id: Mapped[int] = mapped_column(ForeignKey("element.id", ondelete="CASCADE"), nullable=False)
    inspection_id: Mapped[int] = mapped_column(ForeignKey("inspection.id", ondelete="CASCADE"), nullable=False)
    findings: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(String(1))

    element: Mapped[Element] = relationship(back_populates="inspection_results")
    inspection: Mapped[Inspection] = relationship(back_populates="element_inspections")


class ScanJob(Base):
    __tablename__ = "scan_job"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_filename: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(100))
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="UPLOADED", nullable=False, index=True)
    selected_engine: Mapped[str | None] = mapped_column(String(50))
    tesseract_confidence: Mapped[float | None] = mapped_column(Float)
    paddle_confidence: Mapped[float | None] = mapped_column(Float)
    estimated_reliability: Mapped[float | None] = mapped_column(Float)
    raw_text: Mapped[str | None] = mapped_column(Text)
    structured_json: Mapped[str | None] = mapped_column(Text)
    ocr_candidates_json: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)
    inspection_id: Mapped[int | None] = mapped_column(ForeignKey("inspection.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)

    inspection: Mapped[Inspection | None] = relationship()
