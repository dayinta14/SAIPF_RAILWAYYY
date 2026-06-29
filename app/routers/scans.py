from __future__ import annotations

import json

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import ScanJob
from app.repositories import persist_confirmed_scan
from app.schemas import (
    ScanCreateResponse,
    ScanJobResponse,
    ScanResultResponse,
    StructuredInspection,
)
from app.services.file_service import save_upload
from app.services.pipeline_service import process_scan_job


router = APIRouter(prefix="/api/scans", tags=["Scans"])


@router.post("", response_model=ScanCreateResponse, status_code=status.HTTP_202_ACCEPTED)
async def upload_scan(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> ScanCreateResponse:
    path, file_size, stored_name = await save_upload(file)
    job = ScanJob(
        original_filename=file.filename or stored_name,
        stored_filename=stored_name,
        file_path=str(path),
        content_type=file.content_type,
        file_size=file_size,
        status="PROCESSING",
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    background_tasks.add_task(process_scan_job, job.id)
    return ScanCreateResponse(job_id=job.id, filename=job.original_filename, status="PROCESSING")


@router.get("", response_model=list[ScanJobResponse])
def list_scans(limit: int = 50, db: Session = Depends(get_db)) -> list[ScanJob]:
    limit = max(1, min(limit, 200))
    return list(db.scalars(select(ScanJob).order_by(ScanJob.id.desc()).limit(limit)))


@router.get("/{job_id}", response_model=ScanJobResponse)
def get_scan(job_id: int, db: Session = Depends(get_db)) -> ScanJob:
    job = db.get(ScanJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Scan job tidak ditemukan.")
    return job


@router.get("/{job_id}/result", response_model=ScanResultResponse)
def get_scan_result(job_id: int, db: Session = Depends(get_db)) -> ScanResultResponse:
    job = db.get(ScanJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Scan job tidak ditemukan.")

    structured = StructuredInspection.model_validate_json(job.structured_json) if job.structured_json else None
    candidates = json.loads(job.ocr_candidates_json) if job.ocr_candidates_json else []
    return ScanResultResponse(
        job=ScanJobResponse.model_validate(job),
        raw_text=job.raw_text,
        structured=structured,
        candidates=candidates,
    )


@router.put("/{job_id}/result", response_model=ScanResultResponse)
def update_scan_result(
    job_id: int,
    payload: StructuredInspection,
    db: Session = Depends(get_db),
) -> ScanResultResponse:
    job = db.get(ScanJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Scan job tidak ditemukan.")
    if job.status not in {"NEEDS_REVIEW", "FAILED"}:
        raise HTTPException(status_code=409, detail="Hasil hanya dapat diedit pada tahap review.")

    job.structured_json = payload.model_dump_json()
    job.status = "NEEDS_REVIEW"
    job.error_message = None
    db.commit()
    db.refresh(job)

    candidates = json.loads(job.ocr_candidates_json) if job.ocr_candidates_json else []
    return ScanResultResponse(
        job=ScanJobResponse.model_validate(job),
        raw_text=job.raw_text,
        structured=payload,
        candidates=candidates,
    )


@router.post("/{job_id}/confirm", status_code=201)
def confirm_scan(job_id: int, db: Session = Depends(get_db)) -> dict[str, int | str]:
    job = db.get(ScanJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Scan job tidak ditemukan.")
    if job.status == "PROCESSING":
        raise HTTPException(status_code=409, detail="OCR masih diproses.")
    if job.status == "FAILED":
        raise HTTPException(status_code=409, detail="OCR gagal. Periksa error_message.")
    if not job.structured_json:
        raise HTTPException(status_code=422, detail="Hasil terstruktur belum tersedia.")

    structured = StructuredInspection.model_validate_json(job.structured_json)
    try:
        inspection = persist_confirmed_scan(db, job, structured)
        db.commit()
        db.refresh(job)
        return {"job_id": job.id, "inspection_id": inspection.id, "status": job.status}
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception:
        db.rollback()
        raise
