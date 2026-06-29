from __future__ import annotations

import json
import math
import os
import re
import threading
import time
import unicodedata
from dataclasses import asdict, dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import pytesseract
from pytesseract import Output, TesseractNotFoundError
from rapidfuzz import fuzz

from app.config import settings
from app.services.document_service import image_variants


# Railway/Linux menggunakan /usr/bin/tesseract.
# Saat dijalankan lokal di Windows, Tesseract tetap dapat ditemukan melalui PATH.
tesseract_command = os.getenv("TESSERACT_CMD")

if tesseract_command:
    pytesseract.pytesseract.tesseract_cmd = tesseract_command


@dataclass
class OCRItem:
    text: str
    score: float
    box: list[float]


@dataclass
class OCRRun:
    engine: str
    variant: str
    config: str
    text: str
    items: list[OCRItem]
    average_confidence: float
    runtime_seconds: float
    structural_quality: float = 0.0
    agreement: float = 0.0
    estimated_reliability: float = 0.0

    def public_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["items"] = [asdict(item) for item in self.items]
        return data


_paddle_model: Any | None = None
_paddle_lock = threading.Lock()


def clean_text(value: str) -> str:
    value = unicodedata.normalize("NFKC", str(value or ""))
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in value.replace("\r", "\n").split("\n")]
    return "\n".join(line for line in lines if line)


def normalize_compare(value: str) -> str:
    value = clean_text(value).casefold().replace("–", "-").replace("—", "-")
    value = re.sub(r"[^\w%:/.,()\-]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def order_items(items: list[OCRItem]) -> tuple[str, list[OCRItem]]:
    if not items:
        return "", []

    enriched: list[tuple[OCRItem, float, float]] = []
    for item in items:
        x1, y1, x2, y2 = item.box
        enriched.append((item, (y1 + y2) / 2, max(1.0, y2 - y1)))

    median_height = float(np.median([height for _, _, height in enriched]))
    tolerance = max(7.0, median_height * 0.62)
    enriched.sort(key=lambda row: (row[1], row[0].box[0]))

    lines: list[dict[str, Any]] = []
    for item, center_y, height in enriched:
        best_line: dict[str, Any] | None = None
        best_distance = float("inf")
        for line in lines:
            distance = abs(center_y - line["center_y"])
            if distance <= tolerance and distance < best_distance:
                best_line = line
                best_distance = distance
        if best_line is None:
            lines.append({"center_y": center_y, "items": [(item, height)]})
        else:
            best_line["items"].append((item, height))
            best_line["center_y"] = float(
                np.mean([(candidate.box[1] + candidate.box[3]) / 2 for candidate, _ in best_line["items"]])
            )

    lines.sort(key=lambda line: line["center_y"])
    ordered: list[OCRItem] = []
    output_lines: list[str] = []
    for line in lines:
        row = sorted(line["items"], key=lambda pair: pair[0].box[0])
        row_items = [pair[0] for pair in row]
        ordered.extend(row_items)
        typical_height = float(np.median([pair[1] for pair in row]))
        parts: list[str] = []
        previous_right: float | None = None
        for item in row_items:
            if previous_right is not None:
                gap = item.box[0] - previous_right
                parts.append("   " if gap > typical_height * 3 else " ")
            parts.append(item.text)
            previous_right = item.box[2]
        output_lines.append("".join(parts).strip())
    return clean_text("\n".join(output_lines)), ordered


def weighted_confidence(items: list[OCRItem]) -> float:
    if not items:
        return 0.0
    weights = np.array([max(1, len(item.text)) for item in items], dtype=float)
    scores = np.array([item.score for item in items], dtype=float)
    return float(np.average(scores, weights=weights))


def run_tesseract(page_path: Path) -> list[OCRRun]:
    variants = image_variants(page_path)

    try:
        available_languages = set(pytesseract.get_languages(config=""))
    except TesseractNotFoundError as exc:
        raise RuntimeError(
            "Tesseract tidak ditemukan. "
            "Pastikan TESSERACT_CMD=/usr/bin/tesseract pada Railway "
            "atau tesseract.exe sudah masuk PATH pada Windows."
        ) from exc

    language = settings.tesseract_lang
    requested = set(language.split("+"))
    if not requested.issubset(available_languages):
        language = "eng" if "eng" in available_languages else next(iter(available_languages), "eng")

    plans = [
        ("original", "psm3", "--oem 1 --psm 3 -c preserve_interword_spaces=1"),
        ("enhanced", "psm6", "--oem 1 --psm 6 -c preserve_interword_spaces=1"),
    ]
    runs: list[OCRRun] = []

    for variant_name, config_name, config in plans:
        image = variants[variant_name]
        started = time.perf_counter()
        try:
            result = pytesseract.image_to_data(
                cv2.cvtColor(image, cv2.COLOR_BGR2RGB),
                lang=language,
                config=config,
                output_type=Output.DICT,
                timeout=settings.tesseract_timeout_seconds,
            )
        except TesseractNotFoundError as exc:
            raise RuntimeError(
                "Executable Tesseract tidak ditemukan saat OCR dijalankan."
            ) from exc
        except RuntimeError:
            # Biasanya terjadi ketika proses OCR melewati batas timeout.
            continue

        items: list[OCRItem] = []
        for index, raw_text in enumerate(result.get("text", [])):
            text = clean_text(raw_text)
            try:
                confidence = float(result["conf"][index])
            except (TypeError, ValueError):
                confidence = -1.0
            if not text or confidence < 0:
                continue
            x = int(result["left"][index])
            y = int(result["top"][index])
            w = int(result["width"][index])
            h = int(result["height"][index])
            items.append(OCRItem(text, max(0.0, min(1.0, confidence / 100.0)), [x, y, x + w, y + h]))

        text, ordered = order_items(items)
        runs.append(
            OCRRun(
                engine="Tesseract",
                variant=variant_name,
                config=config_name,
                text=text,
                items=ordered,
                average_confidence=weighted_confidence(ordered),
                runtime_seconds=time.perf_counter() - started,
            )
        )
    return runs


def _deep_find(data: Any, key: str) -> Any:
    if isinstance(data, dict):
        if key in data:
            return data[key]
        for value in data.values():
            found = _deep_find(value, key)
            if found is not None:
                return found
    elif isinstance(data, (list, tuple)):
        for value in data:
            found = _deep_find(value, key)
            if found is not None:
                return found
    return None


def _result_payload(result: Any) -> dict[str, Any]:
    if isinstance(result, dict):
        return result
    for attribute in ("json", "res", "data"):
        if not hasattr(result, attribute):
            continue
        value = getattr(result, attribute)
        if callable(value):
            value = value()
        if isinstance(value, str):
            value = json.loads(value)
        if isinstance(value, dict):
            return value
    try:
        return dict(result)
    except Exception as exc:
        raise TypeError(f"Format keluaran PaddleOCR tidak dikenali: {type(result)!r}") from exc


def _box_to_rect(box: Any) -> list[float]:
    array = np.asarray(box, dtype=float)
    if array.ndim == 1 and array.size >= 4:
        return [float(value) for value in array[:4]]
    array = array.reshape(-1, 2)
    return [
        float(array[:, 0].min()),
        float(array[:, 1].min()),
        float(array[:, 0].max()),
        float(array[:, 1].max()),
    ]


def _get_paddle_model() -> Any:
    global _paddle_model
    if _paddle_model is not None:
        return _paddle_model
    with _paddle_lock:
        if _paddle_model is not None:
            return _paddle_model
        from paddleocr import PaddleOCR

        kwargs: dict[str, Any] = {
            "lang": settings.paddle_lang,
            "use_doc_orientation_classify": False,
            "use_doc_unwarping": False,
            "use_textline_orientation": False,
        }
        try:
            _paddle_model = PaddleOCR(device=settings.paddle_device, **kwargs)
        except TypeError:
            _paddle_model = PaddleOCR(**kwargs)
        return _paddle_model


def run_paddle(page_path: Path) -> list[OCRRun]:
    if not settings.enable_paddleocr:
        return []

    model = _get_paddle_model()
    variants = image_variants(page_path)
    runs: list[OCRRun] = []
    for variant_name in ("original", "enhanced"):
        started = time.perf_counter()
        try:
            predictions = list(model.predict(variants[variant_name]))
        except Exception:
            # Some versions are more stable with a file path.
            temp_path = page_path.parent / f"{page_path.stem}_{variant_name}.png"
            cv2.imwrite(str(temp_path), variants[variant_name])
            predictions = list(model.predict(str(temp_path)))

        items: list[OCRItem] = []
        for prediction in predictions:
            payload = _result_payload(prediction)
            texts = list(_deep_find(payload, "rec_texts") or [])
            scores_raw = _deep_find(payload, "rec_scores")
            boxes_raw = _deep_find(payload, "rec_boxes")
            if boxes_raw is None:
                boxes_raw = _deep_find(payload, "rec_polys")
            if scores_raw is None or boxes_raw is None:
                continue
            scores = np.asarray(scores_raw, dtype=float).reshape(-1).tolist()
            boxes = list(np.asarray(boxes_raw, dtype=object))
            for text, score, box in zip(texts, scores, boxes):
                normalized = clean_text(str(text))
                if normalized:
                    items.append(OCRItem(normalized, float(np.clip(score, 0.0, 1.0)), _box_to_rect(box)))

        text, ordered = order_items(items)
        runs.append(
            OCRRun(
                engine="PaddleOCR",
                variant=variant_name,
                config=f"lang={settings.paddle_lang}",
                text=text,
                items=ordered,
                average_confidence=weighted_confidence(ordered),
                runtime_seconds=time.perf_counter() - started,
            )
        )
    return runs


def text_similarity(left: str, right: str) -> float:
    a = normalize_compare(left)
    b = normalize_compare(right)
    if not a or not b:
        return 0.0
    return float(
        0.35 * SequenceMatcher(None, a, b).ratio()
        + 0.35 * (fuzz.token_sort_ratio(a, b) / 100.0)
        + 0.30 * (fuzz.token_set_ratio(a, b) / 100.0)
    )


def structural_quality(text: str) -> float:
    normalized = clean_text(text)
    if not normalized:
        return 0.0
    lines = normalized.splitlines()
    characters = [char for char in normalized if not char.isspace()]
    alphanumeric_ratio = sum(char.isalnum() for char in characters) / max(1, len(characters))
    tokens = re.findall(r"[A-Za-zÀ-ÿ0-9]+(?:[-_/.:][A-Za-zÀ-ÿ0-9]+)*", normalized)
    identifiers = len(re.findall(r"\b[A-Z]{1,10}(?:[-_/][A-Z0-9]{1,16})+\b", normalized, flags=re.I))
    dates = len(re.findall(r"\b(?:0?[1-9]|[12]\d|3[01])[-/.](?:0?[1-9]|1[0-2])[-/.](?:19|20)\d{2}\b", normalized))
    key_values = sum(bool(re.search(r"\S\s*:\s*\S", line)) for line in lines)
    rows = sum(bool(re.match(r"^\s*\d{1,4}\s+[A-Z0-9][A-Z0-9_./-]{2,}", line, flags=re.I)) for line in lines)
    structure = (min(1.0, identifiers / 8) + min(1.0, dates / 2) + min(1.0, key_values / 5) + min(1.0, rows / 8)) / 4
    length = min(1.0, math.log1p(len(tokens)) / math.log(250))
    return float(np.clip(0.45 * alphanumeric_ratio + 0.40 * structure + 0.15 * length, 0.0, 1.0))


def score_and_select(runs: list[OCRRun]) -> OCRRun:
    valid = [run for run in runs if run.text.strip()]
    if not valid:
        raise RuntimeError("Tidak ada mesin OCR yang menghasilkan teks.")

    for index, run in enumerate(valid):
        similarities = [text_similarity(run.text, other.text) for j, other in enumerate(valid) if j != index]
        run.agreement = float(np.mean(similarities)) if similarities else 1.0
        run.structural_quality = structural_quality(run.text)
        run.estimated_reliability = 100.0 * (
            0.52 * run.average_confidence
            + 0.28 * run.agreement
            + 0.20 * run.structural_quality
        )
    return max(valid, key=lambda run: (run.estimated_reliability, run.average_confidence))


def run_ocr_pipeline(page_paths: list[Path]) -> tuple[OCRRun, list[OCRRun]]:
    combined_runs: dict[tuple[str, str, str], list[OCRRun]] = {}

    for page_path in page_paths:
        page_runs = run_tesseract(page_path)
        try:
            page_runs.extend(run_paddle(page_path))
        except Exception as exc:
            # Tesseract remains available if Paddle model cannot load.
            page_runs.append(
                OCRRun(
                    engine="PaddleOCR",
                    variant="error",
                    config="unavailable",
                    text="",
                    items=[],
                    average_confidence=0.0,
                    runtime_seconds=0.0,
                )
            )

        for run in page_runs:
            key = (run.engine, run.variant, run.config)
            combined_runs.setdefault(key, []).append(run)

    merged: list[OCRRun] = []
    for (engine, variant, config), runs in combined_runs.items():
        merged_items: list[OCRItem] = []
        texts: list[str] = []
        confidences: list[float] = []
        runtime = 0.0
        for page_number, run in enumerate(runs, start=1):
            if run.text:
                texts.append(f"=== PAGE {page_number} ===\n{run.text}")
            merged_items.extend(run.items)
            confidences.append(run.average_confidence)
            runtime += run.runtime_seconds
        merged.append(
            OCRRun(
                engine=engine,
                variant=variant,
                config=config,
                text="\n\n".join(texts),
                items=merged_items,
                average_confidence=float(np.mean(confidences)) if confidences else 0.0,
                runtime_seconds=runtime,
            )
        )

    winner = score_and_select(merged)
    return winner, merged
