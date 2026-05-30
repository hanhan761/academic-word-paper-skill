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
    for required in ("abstract", "introduction", "methods", "results", "discussion", "references"):
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
