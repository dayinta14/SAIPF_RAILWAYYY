from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from app.database import SessionLocal
from app.models import ScanJob
from app.services.document_service import render_document
from app.services.nlp_service import structure_ocr_text
from app.services.ocr_service import run_ocr_pipeline


def process_scan_job(job_id: int) -> None:
    session = SessionLocal()
    try:
        job = session.get(ScanJob, job_id)
        if job is None:
            return

        job.status = "PROCESSING"
        job.error_message = None
        session.commit()

        pages = render_document(Path(job.file_path), job.id)
        winner, candidates = run_ocr_pipeline(pages)
        structured = structure_ocr_text(winner.text)

        job.selected_engine = winner.engine
        job.estimated_reliability = winner.estimated_reliability
        job.raw_text = winner.text
        job.structured_json = json.dumps(structured, ensure_ascii=False)
        job.ocr_candidates_json = json.dumps(
            [
                {
                    "engine": run.engine,
                    "variant": run.variant,
                    "config": run.config,
                    "average_confidence": run.average_confidence,
                    "estimated_reliability": run.estimated_reliability,
                    "runtime_seconds": run.runtime_seconds,
                    "text": run.text,
                }
                for run in candidates
            ],
            ensure_ascii=False,
        )

        tesseract_scores = [run.average_confidence for run in candidates if run.engine == "Tesseract"]
        paddle_scores = [run.average_confidence for run in candidates if run.engine == "PaddleOCR" and run.text]
        job.tesseract_confidence = max(tesseract_scores, default=None)
        job.paddle_confidence = max(paddle_scores, default=None)
        job.status = "NEEDS_REVIEW"
        job.completed_at = datetime.utcnow()
        session.commit()

    except Exception as exc:
        session.rollback()
        job = session.get(ScanJob, job_id)
        if job is not None:
            job.status = "FAILED"
            job.error_message = f"{type(exc).__name__}: {exc}"
            job.completed_at = datetime.utcnow()
            session.commit()
    finally:
        session.close()
