from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .ir import export_ir

SECTION_ALIASES = {
    "abstract": {"abstract", "摘要"},
    "introduction": {"introduction", "intro", "引言", "绪论"},
    "methods": {"methods", "materials and methods", "methodology", "方法", "材料与方法"},
    "results": {"results", "结果"},
    "discussion": {"discussion", "讨论"},
    "conclusion": {"conclusion", "conclusions", "结论"},
    "references": {"references", "bibliography", "参考文献"},
    "acknowledgements": {"acknowledgements", "acknowledgments", "致谢"},
    "funding": {"funding", "funding statement", "基金", "资助"},
    "conflict_of_interest": {"conflict of interest", "competing interests", "利益冲突"},
}

KEYWORD_PREFIX_RE = re.compile(r"^\s*(keywords?|关键词)\s*[:：]\s*(.+)$", re.I)
WORD_RE = re.compile(r"[A-Za-z0-9]+(?:[-'][A-Za-z0-9]+)?|[\u4e00-\u9fff]")
FIGURE_CITE_RE = re.compile(r"\b(?:figure|fig\.?)\s*([0-9]+[A-Za-z]?)\b|图\s*([0-9一二三四五六七八九十]+)", re.I)
TABLE_CITE_RE = re.compile(r"\btable\s*([0-9]+[A-Za-z]?)\b|表\s*([0-9一二三四五六七八九十]+)", re.I)
REFERENCE_ITEM_RE = re.compile(r"^\s*(?:\[[0-9]+\]|[0-9]+[.)]|[A-Z][A-Za-z-]+,\s+[A-Z])")


def analyze_writing(docx: str | Path) -> dict[str, Any]:
    ir = export_ir(docx)
    sections = classify_sections(ir)
    title = detect_title(ir, sections)
    abstract = extract_abstract_from_ir(ir, sections)
    keywords = extract_keywords_from_ir(ir)
    references = extract_references_from_ir(ir, sections)
    citation_checks = check_figure_table_citations(ir)
    checks = build_writing_checks(sections, abstract, keywords, references, citation_checks)
    status = "ok" if not checks else "warning"
    return {
        "status": status,
        "title": title,
        "abstract": abstract,
        "keywords": keywords,
        "sections": sections,
        "references": references,
        "citation_checks": citation_checks,
        "checks": checks,
    }


def extract_abstract(docx: str | Path) -> dict[str, Any]:
    report = analyze_writing(docx)
    return report["abstract"]


def list_references(docx: str | Path) -> dict[str, Any]:
    report = analyze_writing(docx)
    return report["references"]


def check_journal(docx: str | Path, rules: str = "basic") -> dict[str, Any]:
    report = analyze_writing(docx)
    checks = list(report["checks"])
    if rules not in {"basic", "nature-basic"}:
        checks.append({"type": "unknown_ruleset", "severity": "warning", "message": f"Unknown ruleset: {rules}"})
    abstract = report["abstract"]
    if abstract.get("word_count", 0) and abstract["word_count"] < 150:
        checks.append(
            {
                "type": "abstract_too_short",
                "severity": "warning",
                "message": "Abstract is under 150 words for the basic journal ruleset.",
                "word_count": abstract["word_count"],
            }
        )
    if abstract.get("word_count", 0) > 250:
        checks.append(
            {
                "type": "abstract_too_long",
                "severity": "warning",
                "message": "Abstract is over 250 words for the basic journal ruleset.",
                "word_count": abstract["word_count"],
            }
        )
    if len(report["keywords"]) > 8:
        checks.append(
            {
                "type": "too_many_keywords",
                "severity": "warning",
                "message": "More than 8 keywords were detected.",
                "keyword_count": len(report["keywords"]),
            }
        )
    return {"status": "ok" if not checks else "warning", "ruleset": rules, "checks": checks, "analysis": report}


def review_manuscript(docx: str | Path) -> dict[str, Any]:
    analysis = analyze_writing(docx)
    ir = export_ir(docx)
    issues = review_issues(analysis, ir)
    categories: dict[str, list[dict[str, Any]]] = {}
    for issue in issues:
        categories.setdefault(issue["category"], []).append(issue)
    return {
        "status": "ok" if not issues else "warning",
        "summary": manuscript_summary(analysis, ir),
        "categories": categories,
        "issues": issues,
        "analysis": analysis,
    }


def plan_revision(docx: str | Path) -> dict[str, Any]:
    review = review_manuscript(docx)
    actions = [revision_action_for_issue(issue, review["analysis"]) for issue in review["issues"]]
    actions = [action for action in actions if action]
    return {
        "status": "ok" if not actions else "action_required",
        "actions": actions,
        "source_issue_count": len(review["issues"]),
        "review_summary": review["summary"],
    }


def make_section_patch(docx: str | Path, section: str, instruction: str = "") -> dict[str, Any]:
    analysis = analyze_writing(docx)
    ir = export_ir(docx)
    section_key = classify_heading(section)
    if section_key == "section":
        section_key = normalize_heading(section)
    target_section = next(
        (
            item
            for item in analysis["sections"]
            if item["type"] == section_key or normalize_heading(item["title"]) == section_key
        ),
        None,
    )
    if not target_section:
        raise ValueError(f"section not found: {section}")
    content_blocks = [
        block
        for block in section_content_blocks(ir, target_section["heading_id"])
        if block.get("type") == "paragraph" and block.get("text", "").strip() and not KEYWORD_PREFIX_RE.match(block.get("text", ""))
    ]
    if not content_blocks:
        raise ValueError(f"section has no editable paragraph blocks: {section}")
    current_text = "\n".join(block["text"].strip() for block in content_blocks)
    return {
        "version": 1,
        "metadata": {
            "kind": "section_rewrite_skeleton",
            "section": target_section["type"],
            "section_title": target_section["title"],
            "instruction": instruction,
            "source_block_ids": [block["id"] for block in content_blocks],
        },
        "actions": [
            {
                "action": "replace_block_text",
                "target": {"block_id": content_blocks[0]["id"]},
                "value": f"TODO: {instruction or 'Rewrite this section.'}\n\nCurrent text:\n{current_text}",
            }
        ],
    }


def classify_sections(ir: dict[str, Any]) -> list[dict[str, Any]]:
    sections: list[dict[str, Any]] = []
    for block in ir.get("blocks", []):
        if block.get("type") != "heading":
            continue
        section_type = classify_heading(block.get("text", ""))
        if not sections and int(block.get("level", 1)) == 1 and section_type == "section":
            section_type = "title"
        sections.append(
            {
                "id": f"sec_{len(sections) + 1:03d}",
                "type": section_type,
                "title": block.get("text", ""),
                "level": block.get("level", 1),
                "heading_id": block.get("id", ""),
            }
        )
    return sections


def manuscript_summary(analysis: dict[str, Any], ir: dict[str, Any]) -> dict[str, Any]:
    body_text = "\n".join(block.get("text", "") for block in ir.get("blocks", []) if block.get("type") == "paragraph")
    return {
        "title": analysis.get("title", ""),
        "word_count": count_words(body_text),
        "section_count": len(analysis.get("sections", [])),
        "figure_count": len(ir.get("figures", [])),
        "table_count": len(ir.get("tables", [])),
        "reference_count": len(analysis.get("references", {}).get("items", [])),
        "issue_count": len(analysis.get("checks", [])),
    }


def review_issues(analysis: dict[str, Any], ir: dict[str, Any]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    priority = 1
    for check in analysis.get("checks", []):
        issue = issue_from_check(check, priority)
        if issue:
            issues.append(issue)
            priority += 1
    abstract = analysis.get("abstract", {})
    if 0 < abstract.get("word_count", 0) < 150:
        issues.append(
            {
                "id": f"issue_{priority:03d}",
                "priority": priority,
                "severity": "major",
                "category": "abstract",
                "type": "abstract_underdeveloped",
                "message": "Abstract is too short for most journal submissions.",
                "rationale": "A usable abstract usually states objective, method, key result, and conclusion.",
                "target": {"section": "abstract", "block_ids": abstract.get("block_ids", [])},
            }
        )
        priority += 1
    for item in analysis.get("references", {}).get("items", []):
        if not item.get("structured"):
            issues.append(
                {
                    "id": f"issue_{priority:03d}",
                    "priority": priority,
                    "severity": "minor",
                    "category": "references",
                    "type": "reference_format_uncertain",
                    "message": "A reference item does not match a simple numbered or author-year pattern.",
                    "rationale": "Reference formatting should be checked before submission.",
                    "target": {"block_id": item.get("block_id")},
                }
            )
            priority += 1
    return sorted(issues, key=lambda item: (severity_rank(item["severity"]), item["priority"]))


def issue_from_check(check: dict[str, Any], priority: int) -> dict[str, Any] | None:
    check_type = check.get("type", "")
    if check_type.startswith("missing_"):
        category = "structure"
        severity = "major"
    elif check_type == "table_not_cited":
        category = "tables"
        severity = "major"
    elif check_type == "figure_not_cited":
        category = "figures"
        severity = "major"
    else:
        category = "writing"
        severity = "minor"
    return {
        "id": f"issue_{priority:03d}",
        "priority": priority,
        "severity": severity,
        "category": category,
        "type": check_type,
        "message": check.get("message", check_type),
        "rationale": rationale_for_check(check_type),
        "target": {"id": check.get("id")} if check.get("id") else {},
    }


def rationale_for_check(check_type: str) -> str:
    if check_type == "table_not_cited":
        return "Every table should be introduced or interpreted in the manuscript body."
    if check_type == "figure_not_cited":
        return "Every figure should be cited where its evidence supports the argument."
    if check_type.startswith("missing_"):
        return "Core manuscript sections make the paper easier to evaluate and submit."
    return "This issue may reduce manuscript clarity or submission readiness."


def revision_action_for_issue(issue: dict[str, Any], analysis: dict[str, Any]) -> dict[str, Any] | None:
    issue_type = issue.get("type", "")
    if issue_type == "abstract_underdeveloped":
        return {
            "action": "rewrite_abstract",
            "priority": issue["priority"],
            "target": issue.get("target", {}),
            "rationale": issue["rationale"],
            "instruction": "Rewrite the abstract to include objective, method, key result, and conclusion in 150-250 words.",
        }
    if issue_type == "table_not_cited":
        return {
            "action": "cite_table",
            "priority": issue["priority"],
            "target": issue.get("target", {}),
            "rationale": issue["rationale"],
            "instruction": "Add a body sentence that cites and interprets the table near the relevant result.",
        }
    if issue_type == "figure_not_cited":
        return {
            "action": "cite_figure",
            "priority": issue["priority"],
            "target": issue.get("target", {}),
            "rationale": issue["rationale"],
            "instruction": "Add a body sentence that cites and interprets the figure near the relevant claim.",
        }
    if issue_type.startswith("missing_"):
        section = issue_type.removeprefix("missing_")
        return {
            "action": "add_section",
            "priority": issue["priority"],
            "target": {"section": section},
            "rationale": issue["rationale"],
            "instruction": f"Add a {section} section with manuscript-appropriate content.",
        }
    return None


def severity_rank(severity: str) -> int:
    return {"critical": 0, "major": 1, "minor": 2}.get(severity, 3)


def classify_heading(text: str) -> str:
    normalized = normalize_heading(text)
    for section_type, aliases in SECTION_ALIASES.items():
        if normalized in {normalize_heading(alias) for alias in aliases}:
            return section_type
    return "section"


def normalize_heading(text: str) -> str:
    text = re.sub(r"^\s*[0-9一二三四五六七八九十IVXivx.、)\-]+\s*", "", text)
    return re.sub(r"\s+", " ", text.strip().lower())


def detect_title(ir: dict[str, Any], sections: list[dict[str, Any]]) -> str:
    for section in sections:
        if section["type"] == "title":
            return section["title"]
    for block in ir.get("blocks", []):
        if block.get("type") == "heading" and int(block.get("level", 1)) == 1:
            return block.get("text", "")
    return ""


def extract_abstract_from_ir(ir: dict[str, Any], sections: list[dict[str, Any]]) -> dict[str, Any]:
    abstract_heading = next((section for section in sections if section["type"] == "abstract"), None)
    if not abstract_heading:
        return {"text": "", "word_count": 0, "block_ids": []}
    blocks = section_content_blocks(ir, abstract_heading["heading_id"])
    text_blocks = []
    block_ids = []
    for block in blocks:
        text = block.get("text", "")
        if KEYWORD_PREFIX_RE.match(text):
            break
        if block.get("type") == "paragraph" and text.strip():
            text_blocks.append(text.strip())
            block_ids.append(block["id"])
    text = "\n".join(text_blocks)
    return {"text": text, "word_count": count_words(text), "block_ids": block_ids}


def extract_keywords_from_ir(ir: dict[str, Any]) -> list[str]:
    for block in ir.get("blocks", []):
        match = KEYWORD_PREFIX_RE.match(block.get("text", ""))
        if match:
            raw_keywords = match.group(2)
            return [item.strip() for item in re.split(r"[;,；，]", raw_keywords) if item.strip()]
    return []


def extract_references_from_ir(ir: dict[str, Any], sections: list[dict[str, Any]]) -> dict[str, Any]:
    references_heading = next((section for section in sections if section["type"] == "references"), None)
    if not references_heading:
        return {"items": [], "section_id": None}
    blocks = section_content_blocks(ir, references_heading["heading_id"])
    items = []
    for block in blocks:
        text = block.get("text", "").strip()
        if block.get("type") == "paragraph" and text:
            items.append({"id": f"ref_{len(items) + 1:03d}", "block_id": block["id"], "text": text, "structured": bool(REFERENCE_ITEM_RE.match(text))})
    return {"items": items, "section_id": references_heading["id"]}


def section_content_blocks(ir: dict[str, Any], heading_id: str) -> list[dict[str, Any]]:
    blocks = ir.get("blocks", [])
    start_index = next((index for index, block in enumerate(blocks) if block.get("id") == heading_id), None)
    if start_index is None:
        return []
    heading_level = int(blocks[start_index].get("level", 1))
    content = []
    for block in blocks[start_index + 1 :]:
        if block.get("type") == "heading" and int(block.get("level", 1)) <= heading_level:
            break
        content.append(block)
    return content


def check_figure_table_citations(ir: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    caption_block_ids = set()
    for figure in ir.get("figures", []):
        caption = figure.get("caption") or {}
        if caption.get("paragraph_id"):
            caption_block_ids.add(caption["paragraph_id"])
    for table in ir.get("tables", []):
        caption = table.get("caption") or {}
        if caption.get("paragraph_id"):
            caption_block_ids.add(caption["paragraph_id"])
    body_text = "\n".join(
        block.get("text", "")
        for block in ir.get("blocks", [])
        if block.get("type") == "paragraph" and block.get("id") not in caption_block_ids
    )
    figure_mentions = citation_numbers(body_text, FIGURE_CITE_RE)
    table_mentions = citation_numbers(body_text, TABLE_CITE_RE)
    return {
        "figures": object_citation_status(ir.get("figures", []), figure_mentions, "figure"),
        "tables": object_citation_status(ir.get("tables", []), table_mentions, "table"),
    }


def citation_numbers(text: str, pattern: re.Pattern[str]) -> set[str]:
    numbers = set()
    for match in pattern.finditer(text):
        number = match.group(1) or match.group(2)
        if number:
            numbers.add(number)
    return numbers


def object_citation_status(items: list[dict[str, Any]], mentions: set[str], kind: str) -> list[dict[str, Any]]:
    statuses = []
    for index, item in enumerate(items, start=1):
        caption = item.get("caption") or {}
        number = str(caption.get("number") or index)
        statuses.append(
            {
                "id": item.get("id", f"{kind}_{index:03d}"),
                "number": number,
                "caption": caption.get("text", ""),
                "cited": number in mentions,
            }
        )
    return statuses


def build_writing_checks(
    sections: list[dict[str, Any]],
    abstract: dict[str, Any],
    keywords: list[str],
    references: dict[str, Any],
    citation_checks: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    section_types = {section["type"] for section in sections}
    for required in ("abstract", "introduction", "methods", "results", "discussion", "conclusion", "references"):
        if required not in section_types:
            checks.append({"type": f"missing_{required}", "severity": "warning", "message": f"Missing {required} section."})
    if not abstract.get("text"):
        checks.append({"type": "missing_abstract_text", "severity": "warning", "message": "Abstract section has no paragraph text."})
    if not keywords:
        checks.append({"type": "missing_keywords", "severity": "warning", "message": "No keyword line was detected."})
    if not references.get("items"):
        checks.append({"type": "missing_references", "severity": "warning", "message": "No reference items were detected."})
    for figure in citation_checks.get("figures", []):
        if not figure["cited"]:
            checks.append({"type": "figure_not_cited", "severity": "warning", "message": f"Figure {figure['number']} is not cited in body text.", "id": figure["id"]})
    for table in citation_checks.get("tables", []):
        if not table["cited"]:
            checks.append({"type": "table_not_cited", "severity": "warning", "message": f"Table {table['number']} is not cited in body text.", "id": table["id"]})
    return checks


def count_words(text: str) -> int:
    return len(WORD_RE.findall(text))
