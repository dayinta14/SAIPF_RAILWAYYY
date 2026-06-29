from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from typing import Any


CATEGORY_ORDER = {"A": 1, "B": 2, "C": 3, "D": 4, "E": 5}

CANONICAL_LABELS: dict[str, list[str]] = {
    "form_no": ["form no", "nomor form", "form number"],
    "revision": ["rev", "revision", "revisi"],
    "equipment_id": ["equipment id", "equipment tag", "tag equipment"],
    "equipment_name": ["equipment name", "nama equipment", "nama peralatan"],
    "location": ["lokasi / area", "lokasi area", "lokasi", "area"],
    "equipment_type": ["tipe equipment", "equipment type", "jenis equipment", "tipe peralatan"],
    "inspection_date": ["tanggal inspeksi", "inspection date", "tanggal"],
    "inspector": ["inspektor", "inspector"],
    "method": ["metode", "method", "inspection method"],
    "status": ["status"],
}


def normalize_space(value: str | None) -> str:
    text = unicodedata.normalize("NFKC", str(value or ""))
    text = text.replace("–", "-").replace("—", "-")
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip(" \t|;,")


def normalize_key(value: str) -> str:
    value = normalize_space(value).casefold()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


ALIAS_TO_CANONICAL = {
    normalize_key(alias): canonical
    for canonical, aliases in CANONICAL_LABELS.items()
    for alias in aliases
}

LABEL_PATTERN = re.compile(
    r"(?i)(?<![A-Za-z0-9])(" + "|".join(
        sorted(
            [re.escape(alias) for aliases in CANONICAL_LABELS.values() for alias in aliases],
            key=len,
            reverse=True,
        )
    ) + r")\s*:\s*"
)


def parse_date(value: str | None) -> str | None:
    value = normalize_space(value)
    for format_string in ("%d-%m-%Y", "%d/%m/%Y", "%d.%m.%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, format_string).date().isoformat()
        except ValueError:
            continue
    return None


def parse_metadata(text: str) -> dict[str, Any]:
    values: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = normalize_space(raw_line)
        matches = list(LABEL_PATTERN.finditer(line))
        for index, match in enumerate(matches):
            start = match.end()
            end = matches[index + 1].start() if index + 1 < len(matches) else len(line)
            canonical = ALIAS_TO_CANONICAL.get(normalize_key(match.group(1)))
            value = normalize_space(line[start:end])
            if canonical and value and canonical not in values:
                values[canonical] = value

    if "inspection_date" not in values:
        date_match = re.search(r"\b(?:0?[1-9]|[12]\d|3[01])[-/.](?:0?[1-9]|1[0-2])[-/.](?:19|20)\d{2}\b", text)
        if date_match:
            values["inspection_date"] = date_match.group(0)

    values["inspection_date"] = parse_date(values.get("inspection_date"))
    return values


def parse_element_line(line: str) -> dict[str, Any] | None:
    line = normalize_space(line)
    match = re.match(r"^\s*(\d{1,4})\s+([A-Za-z0-9][A-Za-z0-9_./-]{1,40})\s+(.+)$", line)
    if not match:
        return None

    content_tokens = match.group(3).split()
    category_indices = [index for index, token in enumerate(content_tokens) if token.upper() in CATEGORY_ORDER]
    if not category_indices:
        return None

    category_index = category_indices[-1]
    category = content_tokens[category_index].upper()
    element_name = normalize_space(" ".join(content_tokens[:category_index]))
    findings = normalize_space(" ".join(content_tokens[category_index + 1:])) or None
    if not element_name:
        return None

    return {
        "row_number": int(match.group(1)),
        "element_tag": normalize_space(match.group(2)),
        "element_name": element_name,
        "category": category,
        "findings": findings,
        "source_line": line,
    }


def parse_elements(text: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    seen: set[tuple[int, str]] = set()
    for line in text.splitlines():
        parsed = parse_element_line(line)
        if not parsed:
            continue
        key = (parsed["row_number"], parsed["element_tag"].casefold())
        if key not in seen:
            seen.add(key)
            records.append(parsed)
    return sorted(records, key=lambda item: item["row_number"])


def overall_condition(elements: list[dict[str, Any]]) -> str | None:
    categories = [item["category"] for item in elements if item.get("category") in CATEGORY_ORDER]
    return max(categories, key=lambda category: CATEGORY_ORDER[category]) if categories else None


def recommendation(elements: list[dict[str, Any]]) -> str | None:
    important = [
        f"{item['element_tag']}: {item['findings']}"
        for item in elements
        if item.get("category") in {"D", "E"} and item.get("findings")
    ]
    return " | ".join(important) or None


def structure_ocr_text(text: str) -> dict[str, Any]:
    metadata = parse_metadata(text)
    elements = parse_elements(text)
    warnings: list[str] = []
    if not metadata.get("equipment_id"):
        warnings.append("Equipment ID belum terdeteksi.")
    if not metadata.get("inspection_date"):
        warnings.append("Tanggal inspeksi belum terdeteksi atau format tidak dikenali.")
    if not metadata.get("inspector"):
        warnings.append("Nama inspektor belum terdeteksi.")
    if not elements:
        warnings.append("Baris elemen inspeksi belum terdeteksi.")

    return {
        "metadata": metadata,
        "elements": elements,
        "overall_condition": overall_condition(elements),
        "recommendation": recommendation(elements),
        "warnings": warnings,
    }
