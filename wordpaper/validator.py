from __future__ import annotations

import re
import zipfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from .ir import export_ir
from .ooxml import DocxPackage


def validate_docx(path: str | Path) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    try:
        package = DocxPackage(path)
    except (zipfile.BadZipFile, FileNotFoundError, PermissionError) as exc:
        return {"status": "error", "errors": [{"type": "invalid_docx_zip", "message": str(exc)}], "warnings": []}

    if "[Content_Types].xml" not in package.parts:
        errors.append({"type": "missing_content_types", "message": "[Content_Types].xml is missing"})
    if "word/document.xml" not in package.parts:
        errors.append({"type": "missing_document_xml", "message": "word/document.xml is missing"})

    for name in package.xml_part_names():
        try:
            package.parse_xml(name)
        except ET.ParseError as exc:
            errors.append({"type": "malformed_xml", "part": name, "message": str(exc)})

    for rel in package.missing_relationship_targets():
        errors.append(
            {
                "type": "missing_relationship_target",
                "message": f"{rel['source_rels']} references missing target {rel['target']}",
                "relationship_id": rel["id"],
                "source_rels": rel["source_rels"],
                "target": rel["target"],
            }
        )

    if "word/document.xml" in package.parts:
        try:
            ir = export_ir(path)
            warnings.extend(validate_academic_structure(ir))
        except Exception as exc:
            errors.append({"type": "ir_parse_failed", "message": str(exc)})

    if errors:
        status = "error"
    elif warnings:
        status = "warning"
    else:
        status = "ok"
    return {"status": status, "errors": errors, "warnings": warnings}


def validate_academic_structure(ir: dict[str, Any]) -> list[dict[str, Any]]:
    warnings: list[dict[str, Any]] = []
    previous_level = 0
    for block in ir.get("blocks", []):
        if block.get("type") != "heading":
            continue
        level = int(block.get("level", 1))
        if previous_level and level > previous_level + 1:
            warnings.append(
                {
                    "type": "heading_level_skip",
                    "message": f"Heading level jumps from {previous_level} to {level}.",
                    "block_id": block["id"],
                }
            )
        if not block.get("text", "").strip():
            warnings.append({"type": "empty_heading", "message": "Heading text is empty.", "block_id": block["id"]})
        previous_level = level

    warnings.extend(duplicate_caption_warnings(ir.get("figures", []), "figure"))
    warnings.extend(duplicate_caption_warnings(ir.get("tables", []), "table"))

    for figure in ir.get("figures", []):
        if not figure.get("caption"):
            warnings.append(
                {
                    "type": "missing_caption",
                    "message": "A figure appears without a nearby caption.",
                    "block_id": figure.get("anchor", {}).get("paragraph_id", figure.get("id")),
                }
            )
    for table in ir.get("tables", []):
        if not table.get("caption"):
            warnings.append(
                {
                    "type": "missing_caption",
                    "message": "A table appears without a nearby caption.",
                    "block_id": table.get("id"),
                }
            )
    return warnings


def duplicate_caption_warnings(items: list[dict[str, Any]], kind: str) -> list[dict[str, Any]]:
    warnings = []
    seen: dict[str, str] = {}
    for item in items:
        caption = item.get("caption") or {}
        number = str(caption.get("number", "")).strip()
        if not number:
            continue
        if number in seen:
            warnings.append(
                {
                    "type": f"duplicate_{kind}_number",
                    "message": f"Duplicate {kind} number {number}.",
                    "block_id": caption.get("paragraph_id", item.get("id")),
                }
            )
        else:
            seen[number] = item.get("id", "")
    return warnings
