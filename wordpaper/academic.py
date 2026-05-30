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
NUMBERED_REFERENCE_RE = re.compile(r"^\s*(?:\[(?P<bracket>[0-9]+)\]|(?P<plain>[0-9]+)[.)])\s*(?P<body>.*)$")
DOI_RE = re.compile(r"\b(?:doi\s*:\s*|https?://(?:dx\.)?doi\.org/)?(10\.[0-9]{4,9}/[-._;()/:A-Z0-9]+)", re.I)
PMID_RE = re.compile(r"\bPMID\s*:?\s*([0-9]+)\b", re.I)
URL_RE = re.compile(r"https?://[^\s)>\]]+", re.I)
YEAR_RE = re.compile(r"\b((?:19|20)[0-9]{2}[a-z]?)\b", re.I)
NUMERIC_CITATION_RE = re.compile(r"\[([0-9,\s;\-]+)\]")
AUTHOR_YEAR_PAREN_RE = re.compile(r"\(([A-Z][A-Za-z'’\-]+)(?:\s+et\s+al\.)?,\s*((?:19|20)[0-9]{2}[a-z]?)\)")
AUTHOR_YEAR_TEXT_RE = re.compile(r"\b([A-Z][A-Za-z'’\-]+)(?:\s+et\s+al\.)?\s*\(((?:19|20)[0-9]{2}[a-z]?)\)")


def analyze_writing(docx: str | Path) -> dict[str, Any]:
    ir = export_ir(docx)
    sections = classify_sections(ir)
    title = detect_title(ir, sections)
    abstract = extract_abstract_from_ir(ir, sections)
    keywords = extract_keywords_from_ir(ir)
    references = extract_references_from_ir(ir, sections)
    reference_audit = audit_references_from_ir(ir, sections, references)
    citation_checks = check_figure_table_citations(ir)
    checks = build_writing_checks(sections, abstract, keywords, references, citation_checks, reference_audit)
    status = "ok" if not checks else "warning"
    return {
        "status": status,
        "title": title,
        "abstract": abstract,
        "keywords": keywords,
        "sections": sections,
        "references": references,
        "reference_audit": reference_audit,
        "citation_checks": citation_checks,
        "checks": checks,
    }


def extract_abstract(docx: str | Path) -> dict[str, Any]:
    report = analyze_writing(docx)
    return report["abstract"]


def list_references(docx: str | Path) -> dict[str, Any]:
    report = analyze_writing(docx)
    return report["references"]


def audit_references(docx: str | Path) -> dict[str, Any]:
    ir = export_ir(docx)
    sections = classify_sections(ir)
    references = extract_references_from_ir(ir, sections)
    return audit_references_from_ir(ir, sections, references)


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
    elif check_type in {
        "citation_without_reference",
        "duplicate_doi",
        "duplicate_reference",
        "missing_year",
        "numbered_reference_sequence_gap",
        "reference_not_cited",
        "unstructured_reference",
    }:
        category = "references"
        severity = "major" if check_type in {"citation_without_reference", "duplicate_doi"} else "minor"
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
    if check_type == "citation_without_reference":
        return "Every in-text citation should resolve to a reference-list item."
    if check_type == "reference_not_cited":
        return "Every reference-list item should support a cited manuscript claim."
    if check_type == "duplicate_doi":
        return "Duplicate identifiers usually mean the same source appears more than once."
    if check_type == "numbered_reference_sequence_gap":
        return "Numbered reference lists should be consecutive before submission."
    if check_type == "missing_year":
        return "Publication year is required for most journal reference styles."
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
            raw_item = {
                "id": f"ref_{len(items) + 1:03d}",
                "block_id": block["id"],
                "text": text,
                "structured": bool(REFERENCE_ITEM_RE.match(text)),
            }
            items.append(parse_reference_item(raw_item))
    return {"items": items, "section_id": references_heading["id"]}


def parse_reference_item(item: dict[str, Any]) -> dict[str, Any]:
    text = item.get("text", "").strip()
    number_match = NUMBERED_REFERENCE_RE.match(text)
    body = number_match.group("body").strip() if number_match else text
    label = (number_match.group("bracket") or number_match.group("plain")) if number_match else ""
    doi_match = DOI_RE.search(text)
    pmid_match = PMID_RE.search(text)
    url_match = URL_RE.search(text)
    year_match = YEAR_RE.search(text)
    authors = extract_reference_authors(body)
    parts = [part.strip() for part in re.split(r"\.\s+", body) if part.strip()]
    title = parts[1] if len(parts) > 1 and authors else (parts[0] if parts else "")
    venue = parts[2] if len(parts) > 2 and authors else (parts[1] if len(parts) > 1 else "")
    parsed = dict(item)
    parsed.update(
        {
            "label": label,
            "style": "numbered" if label else ("author_year" if authors and year_match else "plain"),
            "authors": authors,
            "year": year_match.group(1) if year_match else "",
            "title": cleanup_reference_field(title),
            "venue": cleanup_reference_field(venue),
            "doi": cleanup_identifier(doi_match.group(1)) if doi_match else "",
            "pmid": pmid_match.group(1) if pmid_match else "",
            "url": cleanup_url(url_match.group(0)) if url_match else "",
        }
    )
    parsed["fingerprint"] = reference_fingerprint(parsed)
    parsed["structured"] = bool(parsed["style"] in {"numbered", "author_year"} or item.get("structured"))
    return parsed


def extract_reference_authors(body: str) -> list[str]:
    first_sentence = body.split(".", 1)[0]
    names = re.findall(r"\b([A-Z][A-Za-z'’\-]+)\s+(?:[A-Z]\.?|[A-Z][a-z]+)", first_sentence)
    if names:
        return unique_preserve_order(names)
    first_token = re.match(r"\s*([A-Z][A-Za-z'’\-]+)", first_sentence)
    return [first_token.group(1)] if first_token else []


def cleanup_reference_field(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip(" .")


def cleanup_identifier(value: str) -> str:
    return value.rstrip(".,;").lower()


def cleanup_url(value: str) -> str:
    return value.rstrip(".,;")


def reference_fingerprint(item: dict[str, Any]) -> str:
    if item.get("doi"):
        return f"doi:{item['doi']}"
    if item.get("pmid"):
        return f"pmid:{item['pmid']}"
    basis = "|".join([",".join(item.get("authors", [])), item.get("year", ""), item.get("title", "")]).lower()
    return "text:" + re.sub(r"[^a-z0-9]+", "", basis)


def audit_references_from_ir(ir: dict[str, Any], sections: list[dict[str, Any]], references: dict[str, Any]) -> dict[str, Any]:
    citations = extract_body_citations(ir, sections)
    items = references.get("items", [])
    issues = reference_integrity_issues(items, citations)
    checks = reference_positive_checks(items, citations)
    return {
        "status": "ok" if not issues else "warning",
        "reference_count": len(items),
        "section_id": references.get("section_id"),
        "items": items,
        "citations": citations,
        "checks": checks,
        "issues": issues,
    }


def extract_body_citations(ir: dict[str, Any], sections: list[dict[str, Any]]) -> dict[str, Any]:
    body_text = "\n".join(block.get("text", "") for block in body_blocks_before_references(ir, sections))
    return {"numeric": extract_numeric_citations(body_text), "author_year": extract_author_year_citations(body_text)}


def body_blocks_before_references(ir: dict[str, Any], sections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    reference_heading_id = next((section["heading_id"] for section in sections if section["type"] == "references"), None)
    blocks = ir.get("blocks", [])
    if not reference_heading_id:
        return [block for block in blocks if block.get("type") == "paragraph"]
    body = []
    for block in blocks:
        if block.get("id") == reference_heading_id:
            break
        if block.get("type") == "paragraph":
            body.append(block)
    return body


def extract_numeric_citations(text: str) -> list[str]:
    numbers: list[str] = []
    for match in NUMERIC_CITATION_RE.finditer(text):
        for number in expand_numeric_citation(match.group(1)):
            if number not in numbers:
                numbers.append(number)
    return numbers


def expand_numeric_citation(raw: str) -> list[str]:
    values: list[str] = []
    for part in re.split(r"[,;]", raw):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start_text, end_text = [piece.strip() for piece in part.split("-", 1)]
            if start_text.isdigit() and end_text.isdigit():
                start, end = int(start_text), int(end_text)
                if 0 < start <= end <= start + 100:
                    values.extend(str(value) for value in range(start, end + 1))
                continue
        if part.isdigit():
            values.append(part)
    return values


def extract_author_year_citations(text: str) -> list[dict[str, str]]:
    citations: list[dict[str, str]] = []
    for pattern in (AUTHOR_YEAR_PAREN_RE, AUTHOR_YEAR_TEXT_RE):
        for match in pattern.finditer(text):
            citation = {"author": match.group(1), "year": match.group(2)}
            if citation not in citations:
                citations.append(citation)
    return citations


def reference_integrity_issues(items: list[dict[str, Any]], citations: dict[str, Any]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    numbered = {item["label"]: item for item in items if item.get("label")}
    numeric_citations = set(citations.get("numeric", []))
    for number in citations.get("numeric", []):
        if number not in numbered:
            issues.append(reference_issue("citation_without_reference", "major", f"In-text citation [{number}] has no matching reference item.", {"citation": number}))
    for label, item in numbered.items():
        if label not in numeric_citations and not author_year_item_cited(item, citations.get("author_year", [])):
            issues.append(reference_issue("reference_not_cited", "minor", f"Reference [{label}] is not cited in body text.", {"reference_id": item["id"], "label": label}))
    issues.extend(duplicate_identifier_issues(items, "doi", "duplicate_doi"))
    issues.extend(duplicate_fingerprint_issues(items))
    issues.extend(numbered_sequence_issues(numbered))
    for item in items:
        if not item.get("year"):
            issues.append(reference_issue("missing_year", "minor", "Reference item has no detected publication year.", {"reference_id": item["id"]}))
        if not item.get("structured"):
            issues.append(reference_issue("unstructured_reference", "minor", "Reference item does not match supported numbered or author-year patterns.", {"reference_id": item["id"]}))
    return issues


def reference_positive_checks(items: list[dict[str, Any]], citations: dict[str, Any]) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    numbered = {item["label"]: item for item in items if item.get("label")}
    for number in citations.get("numeric", []):
        if number in numbered:
            checks.append({"type": "reference_numeric_citation_resolved", "citation": number, "reference_id": numbered[number]["id"]})
    for citation in citations.get("author_year", []):
        matches = [item["id"] for item in items if author_year_matches_item(citation, item)]
        if matches:
            checks.append({"type": "reference_author_year_cited", "citation": citation, "reference_ids": matches})
    return checks


def duplicate_identifier_issues(items: list[dict[str, Any]], field: str, issue_type: str) -> list[dict[str, Any]]:
    seen: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        value = item.get(field, "")
        if value:
            seen.setdefault(value, []).append(item)
    issues = []
    for value, duplicates in seen.items():
        if len(duplicates) > 1:
            issues.append(
                reference_issue(
                    issue_type,
                    "major",
                    f"Multiple reference items share {field.upper()} {value}.",
                    {"value": value, "reference_ids": [item["id"] for item in duplicates]},
                )
            )
    return issues


def duplicate_fingerprint_issues(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        fingerprint = item.get("fingerprint", "")
        if fingerprint and fingerprint != "text:":
            seen.setdefault(fingerprint, []).append(item)
    issues = []
    for fingerprint, duplicates in seen.items():
        if len(duplicates) > 1 and not fingerprint.startswith("doi:"):
            issues.append(
                reference_issue(
                    "duplicate_reference",
                    "minor",
                    "Multiple reference items appear to describe the same source.",
                    {"fingerprint": fingerprint, "reference_ids": [item["id"] for item in duplicates]},
                )
            )
    return issues


def numbered_sequence_issues(numbered: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    numeric_labels = sorted(int(label) for label in numbered if label.isdigit())
    if not numeric_labels:
        return []
    expected = list(range(1, numeric_labels[-1] + 1))
    if numeric_labels == expected:
        return []
    missing = [str(value) for value in expected if value not in numeric_labels]
    return [
        reference_issue(
            "numbered_reference_sequence_gap",
            "minor",
            "Numbered references are not consecutive.",
            {"present": [str(value) for value in numeric_labels], "missing": missing},
        )
    ]


def author_year_item_cited(item: dict[str, Any], citations: list[dict[str, str]]) -> bool:
    return any(author_year_matches_item(citation, item) for citation in citations)


def author_year_matches_item(citation: dict[str, str], item: dict[str, Any]) -> bool:
    return citation.get("year", "").lower() == item.get("year", "").lower() and citation.get("author") in item.get("authors", [])


def reference_issue(issue_type: str, severity: str, message: str, detail: dict[str, Any]) -> dict[str, Any]:
    return {"type": issue_type, "severity": severity, "message": message, **detail}


def unique_preserve_order(values: list[str]) -> list[str]:
    result = []
    for value in values:
        if value not in result:
            result.append(value)
    return result


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
    reference_audit: dict[str, Any],
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
    for issue in reference_audit.get("issues", []):
        checks.append(
            {
                "type": issue["type"],
                "severity": issue.get("severity", "warning"),
                "message": issue.get("message", issue["type"]),
                "id": issue.get("reference_id") or issue.get("citation") or issue.get("label"),
            }
        )
    for figure in citation_checks.get("figures", []):
        if not figure["cited"]:
            checks.append({"type": "figure_not_cited", "severity": "warning", "message": f"Figure {figure['number']} is not cited in body text.", "id": figure["id"]})
    for table in citation_checks.get("tables", []):
        if not table["cited"]:
            checks.append({"type": "table_not_cited", "severity": "warning", "message": f"Table {table['number']} is not cited in body text.", "id": table["id"]})
    return checks


def count_words(text: str) -> int:
    return len(WORD_RE.findall(text))
