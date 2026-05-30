from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .academic import (
    analyze_writing,
    audit_references,
    check_journal,
    extract_abstract,
    list_references,
    make_section_patch,
    plan_revision,
    review_manuscript,
)
from .compiler import compile_document
from .ir import export_ir
from .patch import apply_patch
from .quality import evaluate_quality_gate
from .validator import validate_docx


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        result = dispatch(args)
    except Exception as exc:
        print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1
    if result is not None:
        if args.command in {"apply", "compile"}:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            write_result(result, getattr(args, "out", None))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="wordpaper", description="Inspect, patch, and validate academic docx files.")
    sub = parser.add_subparsers(dest="command", required=True)

    inspect = sub.add_parser("inspect", help="Summarize document structure.")
    inspect.add_argument("docx")
    inspect.add_argument("--out")

    export_ir_cmd = sub.add_parser("export-ir", help="Export WordPaper IR as JSON.")
    export_ir_cmd.add_argument("docx")
    export_ir_cmd.add_argument("--out", required=True)

    for command, key in [
        ("list-sections", "sections"),
        ("list-figures", "figures"),
        ("list-tables", "tables"),
        ("extract-comments", "comments"),
    ]:
        cmd = sub.add_parser(command, help=f"Export {key}.")
        cmd.add_argument("docx")
        cmd.add_argument("--out")
        cmd.set_defaults(result_key=key)

    apply_cmd = sub.add_parser("apply", help="Apply JSON or YAML patch to a docx.")
    apply_cmd.add_argument("docx")
    apply_cmd.add_argument("patch")
    apply_cmd.add_argument("--out", required=True)

    validate = sub.add_parser("validate", help="Validate docx integrity and academic structure.")
    validate.add_argument("docx")
    validate.add_argument("--out")

    diff = sub.add_parser("diff", help="Generate a basic semantic diff between two docx files.")
    diff.add_argument("old_docx")
    diff.add_argument("new_docx")
    diff.add_argument("--out")

    export_md = sub.add_parser("export-md", help="Export readable Markdown from the document IR.")
    export_md.add_argument("docx")
    export_md.add_argument("--out", required=True)

    analyze = sub.add_parser("analyze-writing", help="Analyze academic writing structure and paper semantics.")
    analyze.add_argument("docx")
    analyze.add_argument("--out")

    abstract = sub.add_parser("extract-abstract", help="Extract the abstract text and word count.")
    abstract.add_argument("docx")
    abstract.add_argument("--out")

    refs = sub.add_parser("list-references", help="Extract reference-section items.")
    refs.add_argument("docx")
    refs.add_argument("--out")

    ref_audit = sub.add_parser("audit-references", help="Audit reference metadata and in-text citation integrity.")
    ref_audit.add_argument("docx")
    ref_audit.add_argument("--out")

    journal = sub.add_parser("check-journal", help="Run basic journal-style manuscript checks.")
    journal.add_argument("docx")
    journal.add_argument("--rules", default="basic")
    journal.add_argument("--out")

    review = sub.add_parser("review-manuscript", help="Generate prioritized manuscript review issues.")
    review.add_argument("docx")
    review.add_argument("--out")

    plan = sub.add_parser("plan-revision", help="Generate an actionable revision plan from manuscript review.")
    plan.add_argument("docx")
    plan.add_argument("--out")

    section_patch = sub.add_parser("make-section-patch", help="Create a JSON patch skeleton for rewriting a section.")
    section_patch.add_argument("docx")
    section_patch.add_argument("--section", required=True)
    section_patch.add_argument("--instruction", default="")
    section_patch.add_argument("--out", required=True)

    compile_cmd = sub.add_parser("compile", help="Compile a semantic WordPaper plan into a revised docx and report.")
    compile_cmd.add_argument("docx")
    compile_cmd.add_argument("plan")
    compile_cmd.add_argument("--out", required=True)
    compile_cmd.add_argument("--report")

    quality = sub.add_parser("quality-gate", help="Run six-category 100-percent quality gate against a gold file.")
    quality.add_argument("docx")
    quality.add_argument("--gold", required=True)
    quality.add_argument("--compile-plan", required=True)
    quality.add_argument("--compiled-out", required=True)
    quality.add_argument("--require-100", action="store_true")
    quality.add_argument("--out", required=True)

    return parser


def dispatch(args: argparse.Namespace) -> Any:
    if args.command == "inspect":
        ir = export_ir(args.docx)
        return {
            "status": "ok",
            "block_count": len(ir["blocks"]),
            "section_count": len(ir["sections"]),
            "figure_count": len(ir["figures"]),
            "table_count": len(ir["tables"]),
            "footnote_count": len(ir["footnotes"]),
            "comment_count": len(ir["comments"]),
            "sections": ir["sections"],
        }
    if args.command == "export-ir":
        return export_ir(args.docx)
    if args.command in {"list-sections", "list-figures", "list-tables", "extract-comments"}:
        ir = export_ir(args.docx)
        return ir[args.result_key]
    if args.command == "apply":
        return apply_patch(args.docx, args.patch, args.out)
    if args.command == "validate":
        return validate_docx(args.docx)
    if args.command == "diff":
        return diff_docs(args.old_docx, args.new_docx)
    if args.command == "export-md":
        markdown = export_markdown(args.docx)
        Path(args.out).write_text(markdown, encoding="utf-8")
        return None
    if args.command == "analyze-writing":
        return analyze_writing(args.docx)
    if args.command == "extract-abstract":
        return extract_abstract(args.docx)
    if args.command == "list-references":
        return list_references(args.docx)
    if args.command == "audit-references":
        return audit_references(args.docx)
    if args.command == "check-journal":
        return check_journal(args.docx, args.rules)
    if args.command == "review-manuscript":
        return review_manuscript(args.docx)
    if args.command == "plan-revision":
        return plan_revision(args.docx)
    if args.command == "make-section-patch":
        return make_section_patch(args.docx, args.section, args.instruction)
    if args.command == "compile":
        return compile_document(args.docx, args.plan, args.out, args.report)
    if args.command == "quality-gate":
        report = evaluate_quality_gate(args.docx, args.gold, args.compile_plan, args.compiled_out)
        Path(args.out).write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        if args.require_100 and report["overall_score"] < 100:
            raise ValueError(f"quality gate failed: {report['overall_score']}")
        return None
    raise ValueError(f"unknown command: {args.command}")


def write_result(result: Any, out_path: str | None) -> None:
    if out_path:
        Path(out_path).write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    else:
        print(json.dumps(result, indent=2, ensure_ascii=False))


def diff_docs(old_docx: str | Path, new_docx: str | Path) -> dict[str, Any]:
    old_ir = export_ir(old_docx)
    new_ir = export_ir(new_docx)
    old_blocks = {block["id"]: block for block in old_ir["blocks"]}
    new_blocks = {block["id"]: block for block in new_ir["blocks"]}
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


def export_markdown(docx: str | Path) -> str:
    ir = export_ir(docx)
    lines = []
    for block in ir["blocks"]:
        if block["type"] == "heading":
            lines.append(f"{'#' * int(block.get('level', 1))} {block['text']}")
            lines.append("")
        elif block["type"] == "paragraph":
            if block.get("text"):
                lines.append(block["text"])
                lines.append("")
        elif block["type"] == "table":
            rows = [[cell["text"] for cell in row["cells"]] for row in block["rows"]]
            if rows:
                lines.append("| " + " | ".join(rows[0]) + " |")
                lines.append("| " + " | ".join("---" for _ in rows[0]) + " |")
                for row in rows[1:]:
                    lines.append("| " + " | ".join(row) + " |")
                lines.append("")
    return "\n".join(lines).rstrip() + "\n"
