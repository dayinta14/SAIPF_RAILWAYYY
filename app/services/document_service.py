from __future__ import annotations

from pathlib import Path

import cv2
import fitz
import numpy as np

from app.config import settings


class DocumentProcessingError(RuntimeError):
    pass


def render_document(file_path: Path, job_id: int) -> list[Path]:
    output_dir = settings.processed_dir / str(job_id) / "pages"
    output_dir.mkdir(parents=True, exist_ok=True)
    extension = file_path.suffix.lower()
    output_paths: list[Path] = []

    if extension == ".pdf":
        try:
            document = fitz.open(file_path)
            zoom = settings.render_dpi / 72.0
            matrix = fitz.Matrix(zoom, zoom)
            for index, page in enumerate(document):
                pixmap = page.get_pixmap(matrix=matrix, alpha=False)
                output_path = output_dir / f"page_{index + 1:03d}.png"
                pixmap.save(str(output_path))
                output_paths.append(output_path)
            document.close()
        except Exception as exc:
            raise DocumentProcessingError(f"PDF tidak dapat dirender: {exc}") from exc
    else:
        image = cv2.imread(str(file_path), cv2.IMREAD_COLOR)
        if image is None:
            raise DocumentProcessingError("Gambar tidak dapat dibaca.")
        output_path = output_dir / "page_001.png"
        cv2.imwrite(str(output_path), image)
        output_paths.append(output_path)

    if not output_paths:
        raise DocumentProcessingError("Dokumen tidak memiliki halaman yang dapat diproses.")
    return output_paths


def enhance_image(image: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=1.8, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)
    blurred = cv2.GaussianBlur(enhanced, (0, 0), 1.0)
    sharpened = cv2.addWeighted(enhanced, 1.55, blurred, -0.55, 0)
    return cv2.cvtColor(sharpened, cv2.COLOR_GRAY2BGR)


def image_variants(image_path: Path) -> dict[str, np.ndarray]:
    image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
    if image is None:
        raise DocumentProcessingError(f"Halaman tidak dapat dibaca: {image_path}")
    return {
        "original": image,
        "enhanced": enhance_image(image),
    }
