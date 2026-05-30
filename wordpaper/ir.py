from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from .ooxml import A_NS, DocxPackage, R_NS, W_NS, qn, r_attr, text_content, w_tag

FIGURE_RE = re.compile(r"^\s*(figure|fig\.?|图)\s*([0-9一二三四五六七八九十]+)[\s.．:：-]*(.*)", re.I)
TABLE_RE = re.compile(r"^\s*(table|表)\s*([0-9一二三四五六七八九十]+)[\s.．:：-]*(.*)", re.I)
HEADING_RE = re.compile(r"^(heading\s*|标题\s*)([1-9])$", re.I)


def export_ir(path: str | Path) -> dict[str, Any]:
    package = DocxPackage(path)
    styles = parse_styles(package)
    document = package.parse_xml("word/document.xml")
    body = document.find(f".//{w_tag('body')}")
    blocks = parse_body_blocks(body, styles, package.document_relationships_by_id()) if body is not None else []

    figures = detect_figures(blocks, package.document_relationships_by_id())
    tables = detect_tables(blocks)
    sections = detect_sections(blocks)

    return {
        "version": 1,
        "id": "doc_001",
        "type": "academic_paper",
        "source": str(Path(path)),
        "metadata": parse_metadata(package),
        "styles": styles,
        "sections": sections,
        "blocks": blocks,
        "figures": figures,
        "tables": tables,
        "footnotes": parse_notes(package, "word/footnotes.xml", "footnote"),
        "endnotes": parse_notes(package, "word/endnotes.xml", "endnote"),
        "comments": parse_comments(package),
        "relationships": package.relationships(),
        "media": package.media_parts(),
    }


def parse_styles(package: DocxPackage) -> dict[str, dict[str, str]]:
    root = package.parse_xml_optional("word/styles.xml")
    if root is None:
        return {}
    styles: dict[str, dict[str, str]] = {}
    for style in root.findall(f".//{w_tag('style')}"):
        style_id = style.attrib.get(qn(W_NS, "styleId"), "")
        if not style_id:
            continue
        name_el = style.find(w_tag("name"))
        styles[style_id] = {
            "id": style_id,
            "name": name_el.attrib.get(qn(W_NS, "val"), style_id) if name_el is not None else style_id,
            "type": style.attrib.get(qn(W_NS, "type"), ""),
        }
    return styles


def parse_metadata(package: DocxPackage) -> dict[str, str]:
    metadata: dict[str, str] = {}
    core = package.parse_xml_optional("docProps/core.xml")
    if core is None:
        return metadata
    for child in list(core):
        key = child.tag.split("}", 1)[-1]
        if child.text:
            metadata[key] = child.text
    return metadata


def parse_body_blocks(
    body: ET.Element,
    styles: dict[str, dict[str, str]],
    document_rels: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    counters = {"paragraph": 0, "heading": 0, "table": 0}
    body_children = list(body)
    for body_index, child in enumerate(body_children, start=1):
        if child.tag == w_tag("p"):
            style = paragraph_style(child)
            level = heading_level(style, styles)
            runs = paragraph_runs(child)
            text = "".join(run["text"] for run in runs)
            media_refs = paragraph_media_refs(child, document_rels)
            if level:
                counters["heading"] += 1
                block_id = f"h_{counters['heading']:03d}"
                block_type = "heading"
            else:
                counters["paragraph"] += 1
                block_id = f"p_{counters['paragraph']:03d}"
                block_type = "paragraph"
            block: dict[str, Any] = {
                "id": block_id,
                "type": block_type,
                "text": text,
                "style": style,
                "runs": runs,
                "location": location(body_index),
            }
            if level:
                block["level"] = level
            if media_refs:
                block["media_refs"] = media_refs
            blocks.append(block)
        elif child.tag == w_tag("tbl"):
            counters["table"] += 1
            rows = table_rows(child)
            blocks.append(
                {
                    "id": f"tbl_{counters['table']:03d}",
                    "type": "table",
                    "text": table_text(rows),
                    "rows": rows,
                    "style": table_style(child),
                    "location": location(body_index),
                }
            )
    return blocks


def paragraph_style(paragraph: ET.Element) -> str:
    style = paragraph.find(f"{w_tag('pPr')}/{w_tag('pStyle')}")
    return style.attrib.get(qn(W_NS, "val"), "Normal") if style is not None else "Normal"


def heading_level(style_id: str, styles: dict[str, dict[str, str]]) -> int | None:
    candidates = [style_id, styles.get(style_id, {}).get("name", "")]
    for candidate in candidates:
        normalized = re.sub(r"[\s_-]+", "", candidate.strip().lower())
        match = re.match(r"heading([1-9])$", normalized)
        if match:
            return int(match.group(1))
        zh_match = re.match(r"标题([1-9])$", normalized)
        if zh_match:
            return int(zh_match.group(1))
    return None


def paragraph_runs(paragraph: ET.Element) -> list[dict[str, Any]]:
    runs: list[dict[str, Any]] = []
    for run in paragraph.findall(w_tag("r")):
        text = text_content(run)
        props = run.find(w_tag("rPr"))
        vert = props.find(w_tag("vertAlign")) if props is not None else None
        runs.append(
            {
                "text": text,
                "bold": props is not None and props.find(w_tag("b")) is not None,
                "italic": props is not None and props.find(w_tag("i")) is not None,
                "superscript": vert is not None and vert.attrib.get(qn(W_NS, "val")) == "superscript",
                "subscript": vert is not None and vert.attrib.get(qn(W_NS, "val")) == "subscript",
            }
        )
    return runs


def paragraph_media_refs(
    paragraph: ET.Element,
    document_rels: dict[str, dict[str, Any]],
) -> list[dict[str, str]]:
    refs: list[dict[str, str]] = []
    for blip in paragraph.findall(f".//{{{A_NS}}}blip"):
        rid = blip.attrib.get(r_attr("embed")) or blip.attrib.get(r_attr("link"))
        if not rid:
            continue
        rel = document_rels.get(rid, {})
        refs.append({"relationship_id": rid, "target": rel.get("resolved_target", "")})
    return refs


def table_style(table: ET.Element) -> str:
    style = table.find(f"{w_tag('tblPr')}/{w_tag('tblStyle')}")
    return style.attrib.get(qn(W_NS, "val"), "") if style is not None else ""


def table_rows(table: ET.Element) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for tr in table.findall(w_tag("tr")):
        cells = []
        for tc in tr.findall(w_tag("tc")):
            cells.append({"text": text_content(tc)})
        rows.append({"cells": cells})
    return rows


def table_text(rows: list[dict[str, Any]]) -> str:
    return "\n".join("\t".join(cell["text"] for cell in row["cells"]) for row in rows)


def detect_figures(
    blocks: list[dict[str, Any]],
    document_rels: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    figures: list[dict[str, Any]] = []
    for index, block in enumerate(blocks):
        if not block.get("media_refs"):
            continue
        caption = nearby_caption(blocks, index, FIGURE_RE)
        media_refs = block.get("media_refs", [])
        figures.append(
            {
                "id": f"fig_{len(figures) + 1:03d}",
                "type": "figure",
                "image_ref": media_refs[0].get("target") if media_refs else "",
                "media_refs": media_refs,
                "caption": caption,
                "anchor": {"paragraph_id": block["id"]},
                "cross_refs": [],
            }
        )
    return figures


def detect_tables(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    tables: list[dict[str, Any]] = []
    for index, block in enumerate(blocks):
        if block["type"] != "table":
            continue
        tables.append(
            {
                "id": block["id"],
                "type": "table",
                "caption": nearby_caption(blocks, index, TABLE_RE),
                "rows": block["rows"],
                "style": block.get("style", ""),
                "anchor": {"block_id": block["id"]},
            }
        )
    return tables


def nearby_caption(blocks: list[dict[str, Any]], index: int, pattern: re.Pattern[str]) -> dict[str, Any] | None:
    for candidate_index in (index + 1, index - 1):
        if 0 <= candidate_index < len(blocks):
            candidate = blocks[candidate_index]
            text = candidate.get("text", "")
            match = pattern.match(text)
            if match:
                return {
                    "text": text,
                    "paragraph_id": candidate["id"],
                    "number": match.group(2),
                }
    return None


def detect_sections(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sections: list[dict[str, Any]] = []
    for block in blocks:
        if block["type"] == "heading":
            sections.append(
                {
                    "id": f"sec_{len(sections) + 1:03d}",
                    "title": block["text"],
                    "level": block.get("level", 1),
                    "heading_id": block["id"],
                    "type": classify_section(block["text"]),
                }
            )
    return sections


def classify_section(title: str) -> str:
    normalized = title.strip().lower()
    if normalized in {"abstract", "摘要"}:
        return "abstract"
    if normalized in {"references", "bibliography", "参考文献"}:
        return "references"
    if normalized in {"acknowledgements", "acknowledgments", "致谢"}:
        return "acknowledgements"
    return "section"


def parse_notes(package: DocxPackage, part_name: str, tag_name: str) -> list[dict[str, str]]:
    root = package.parse_xml_optional(part_name)
    if root is None:
        return []
    notes: list[dict[str, str]] = []
    for note in root.findall(w_tag(tag_name)):
        note_id = note.attrib.get(qn(W_NS, "id"), "")
        if is_special_note_id(note_id):
            continue
        notes.append({"id": note_id, "text": text_content(note)})
    return notes


def is_special_note_id(note_id: str) -> bool:
    try:
        return int(note_id) < 1
    except ValueError:
        return False


def parse_comments(package: DocxPackage) -> list[dict[str, str]]:
    root = package.parse_xml_optional("word/comments.xml")
    if root is None:
        return []
    comments: list[dict[str, str]] = []
    for comment in root.findall(w_tag("comment")):
        comments.append(
            {
                "id": comment.attrib.get(qn(W_NS, "id"), ""),
                "author": comment.attrib.get(qn(W_NS, "author"), ""),
                "text": text_content(comment),
            }
        )
    return comments


def location(body_index: int) -> dict[str, Any]:
    return {
        "part": "word/document.xml",
        "body_index": body_index,
        "xpath": f"/w:document/w:body/*[{body_index}]",
    }


def caption_kind(text: str) -> str | None:
    if FIGURE_RE.match(text):
        return "figure"
    if TABLE_RE.match(text):
        return "table"
    return None
