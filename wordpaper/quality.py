from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .academic import analyze_writing, check_journal, plan_revision, review_manuscript
from .compiler import compile_document
from .ir import export_ir
from .validator import validate_docx


def evaluate_quality_gate(
    docx: str | Path,
    gold: str | Path | dict[str, Any],
    compile_plan: str | Path | dict[str, Any],
    compiled_out: str | Path,
) -> dict[str, Any]:
    gold_data = load_json_like(gold)
    analysis = analyze_writing(docx)
    ir = export_ir(docx)
    validation = validate_docx(docx)
    review = review_manuscript(docx)
    revision = plan_revision(docx)
    compile_report = compile_document(docx, compile_plan, compiled_out)
    compiled_analysis = analyze_writing(compiled_out) if compile_report["status"] != "error" else {}
    categories = [
        score_category("word_safety", word_safety_checks(validation, compile_report)),
        score_category("structure_analysis", structure_checks(analysis, ir, gold_data)),
        score_category("writing_assist", writing_checks(review, revision, gold_data)),
        score_category("submission_prep", submission_checks(docx)),
        score_category("citation_system", citation_checks(analysis, compiled_analysis, gold_data)),
        score_category("end_to_end", end_to_end_checks(compile_report, compiled_analysis)),
    ]
    overall = min(category["score"] for category in categories)
    return {
        "status": "pass" if overall == 100 else "fail",
        "overall_score": overall,
        "categories": categories,
        "supported_scope": "Scores are exact for the supplied gold corpus and supported WordPaper feature set, not universal Word coverage.",
    }


def load_json_like(value: str | Path | dict[str, Any]) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return json.loads(Path(value).read_text(encoding="utf-8"))


def score_category(name: str, checks: list[dict[str, Any]]) -> dict[str, Any]:
    passed = sum(1 for item in checks if item["passed"])
    score = 100 if not checks else round(100 * passed / len(checks))
    return {"name": name, "score": score, "checks": checks}


def check(name: str, passed: bool, detail: Any = None) -> dict[str, Any]:
    result = {"name": name, "passed": bool(passed)}
    if detail is not None:
        result["detail"] = detail
    return result


def word_safety_checks(validation: dict[str, Any], compile_report: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        check("input_validation_ok", validation["status"] == "ok", validation),
        check("compile_patch_ok", compile_report["patch"]["status"] == "ok", compile_report["patch"]),
        check("compiled_validation_ok", compile_report["validation"]["status"] == "ok", compile_report["validation"]),
        check("semantic_diff_present", bool(compile_report["diff"]["changes"]), compile_report["diff"]),
    ]


def structure_checks(analysis: dict[str, Any], ir: dict[str, Any], gold: dict[str, Any]) -> list[dict[str, Any]]:
    section_types = [section["type"] for section in analysis["sections"]]
    return [
        check("title_matches", analysis["title"] == gold.get("title"), analysis["title"]),
        check("abstract_contains_expected_text", gold.get("abstract_contains", "") in analysis["abstract"]["text"], analysis["abstract"]["text"]),
        check("keywords_match", set(analysis["keywords"]) == set(gold.get("keywords", [])), analysis["keywords"]),
        check("sections_match", section_types == gold.get("sections", []), section_types),
        check("figure_count_matches", len(ir.get("figures", [])) == gold.get("figures", 0), len(ir.get("figures", []))),
        check("table_count_matches", len(ir.get("tables", [])) == gold.get("tables", 0), len(ir.get("tables", []))),
        check("reference_count_matches", len(analysis["references"]["items"]) == gold.get("references", 0), len(analysis["references"]["items"])),
    ]


def writing_checks(review: dict[str, Any], revision: dict[str, Any], gold: dict[str, Any]) -> list[dict[str, Any]]:
    issue_types = {issue["type"] for issue in review["issues"]}
    action_types = {action["action"] for action in revision["actions"]}
    return [
        check("review_has_prioritized_issues", bool(review["issues"]) and all("priority" in issue for issue in review["issues"]), review["issues"]),
        check("required_review_issue_types_present", set(gold.get("requires_review_issue_types", [])) <= issue_types, sorted(issue_types)),
        check("revision_plan_has_actions", bool(revision["actions"]), revision["actions"]),
        check("required_revision_actions_present", set(gold.get("requires_revision_actions", [])) <= action_types, sorted(action_types)),
    ]


def submission_checks(docx: str | Path) -> list[dict[str, Any]]:
    journal = check_journal(docx, "basic")
    check_types = {item["type"] for item in journal["checks"]}
    return [
        check("journal_check_runs", journal["status"] in {"ok", "warning"}, journal["status"]),
        check("abstract_length_checked", "abstract_too_short" in check_types or "abstract_too_long" in check_types or journal["status"] == "ok", sorted(check_types)),
        check("structure_requirements_checked", any(item.startswith("missing_") for item in check_types), sorted(check_types)),
    ]


def citation_checks(analysis: dict[str, Any], compiled_analysis: dict[str, Any], gold: dict[str, Any]) -> list[dict[str, Any]]:
    before_tables = analysis["citation_checks"]["tables"]
    after_tables = compiled_analysis.get("citation_checks", {}).get("tables", [])
    reference_audit = analysis.get("reference_audit", {})
    reference_issue_types = {issue["type"] for issue in reference_audit.get("issues", [])}
    reference_items = reference_audit.get("items", [])
    return [
        check("references_extracted", len(analysis["references"]["items"]) == gold.get("references", 0), analysis["references"]),
        check("reference_audit_runs", reference_audit.get("status") in {"ok", "warning"}, reference_audit.get("status")),
        check("reference_metadata_parsed", all(item.get("label") and item.get("year") for item in reference_items), reference_items),
        check("required_reference_issue_types_present", set(gold.get("requires_reference_issue_types", [])) <= reference_issue_types, sorted(reference_issue_types)),
        check("uncited_table_detected", any(not item["cited"] for item in before_tables), before_tables),
        check("table_citation_compiled", bool(after_tables) and all(item["cited"] for item in after_tables), after_tables),
    ]


def end_to_end_checks(compile_report: dict[str, Any], compiled_analysis: dict[str, Any]) -> list[dict[str, Any]]:
    section_types = {section["type"] for section in compiled_analysis.get("sections", [])}
    keywords = set(compiled_analysis.get("keywords", []))
    return [
        check("compile_status_ok", compile_report["status"] == "ok", compile_report["status"]),
        check("output_has_conclusion", "conclusion" in section_types, sorted(section_types)),
        check("output_keywords_updated", "semantic compiler" in keywords, sorted(keywords)),
        check("output_abstract_updated", "semantic compiler" in compiled_analysis.get("abstract", {}).get("text", ""), compiled_analysis.get("abstract", {})),
    ]
