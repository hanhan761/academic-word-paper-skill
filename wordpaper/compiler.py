from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .ir import export_ir
from .patch import apply_patch, load_patch
from .validator import validate_docx


def compile_document(
    input_docx: str | Path,
    plan: dict[str, Any] | str | Path,
    out_docx: str | Path,
    report_out: str | Path | None = None,
) -> dict[str, Any]:
    plan_data = load_patch(plan)
    before_ir = export_ir(input_docx)
    patch_report = apply_patch(input_docx, plan_data, out_docx)
    if patch_report["status"] != "ok":
        report = {
            "status": "error",
            "input": str(input_docx),
            "output": str(out_docx),
            "patch": patch_report,
            "validation": None,
            "diff": None,
        }
        write_report(report, report_out)
        return report

    validation = validate_docx(out_docx)
    after_ir = export_ir(out_docx)
    diff = semantic_diff(before_ir, after_ir)
    if validation["status"] == "error":
        status = "error"
    elif validation["status"] == "warning":
        status = "warning"
    else:
        status = "ok"
    report = {
        "status": status,
        "input": str(input_docx),
        "output": str(out_docx),
        "action_count": len(plan_data.get("actions", [])),
        "patch": patch_report,
        "validation": validation,
        "diff": diff,
    }
    write_report(report, report_out)
    return report


def semantic_diff(old_ir: dict[str, Any], new_ir: dict[str, Any]) -> dict[str, Any]:
    old_blocks = {block["id"]: block for block in old_ir.get("blocks", [])}
    new_blocks = {block["id"]: block for block in new_ir.get("blocks", [])}
    changes = []
    for block_id, old_block in old_blocks.items():
        new_block = new_blocks.get(block_id)
        if new_block is None:
            changes.append({"type": "deleted_block", "block_id": block_id, "old_text": old_block.get("text", "")})
        elif old_block.get("text") != new_block.get("text"):
            changes.append(
                {
                    "type": "changed_text",
                    "block_id": block_id,
                    "old_text": old_block.get("text", ""),
                    "new_text": new_block.get("text", ""),
                }
            )
    for block_id, new_block in new_blocks.items():
        if block_id not in old_blocks:
            changes.append({"type": "inserted_block", "block_id": block_id, "new_text": new_block.get("text", "")})
    return {"status": "ok", "changes": changes}


def write_report(report: dict[str, Any], report_out: str | Path | None) -> None:
    if report_out:
        Path(report_out).write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
