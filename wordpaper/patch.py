from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from .ir import detect_figures, detect_sections, detect_tables, export_ir, parse_body_blocks, parse_styles
from .ooxml import DocxPackage, qn, w_tag, xml_bytes

KEYWORD_PREFIX_RE = r"^\s*(keywords?|关键词)\s*[:：]"


def apply_patch(input_docx: str | Path, patch: dict[str, Any] | str | Path, out_docx: str | Path) -> dict[str, Any]:
    patch_data = load_patch(patch)
    package = DocxPackage(input_docx)
    document = package.parse_xml("word/document.xml")
    body = document.find(f".//{w_tag('body')}")
    if body is None:
        return {"status": "error", "applied": [], "errors": [{"message": "word/document.xml has no body"}]}

    ir = current_ir(package, body)
    applied: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for action in patch_data.get("actions", []):
        try:
            applied.append(apply_action(action, body, ir))
            ir = current_ir(package, body)
        except Exception as exc:  # Keep batch patch reports explicit instead of half-silent.
            errors.append({"action": action.get("action", ""), "message": str(exc)})

    if errors:
        return {"status": "error", "applied": applied, "errors": errors}

    package.write(out_docx, {"word/document.xml": xml_bytes(document)})
    return {"status": "ok", "applied": applied, "errors": []}


def apply_action(action: dict[str, Any], body: ET.Element, ir: dict[str, Any]) -> dict[str, Any]:
    action_name = action.get("action") or action.get("type")
    if action_name == "replace_block_text":
        block = find_target_block(ir, action.get("target", {}))
        replace_paragraph_text(body_child(body, block), str(action.get("value", "")))
        return {"action": action_name, "block_id": block["id"]}
    if action_name == "insert_after":
        block = find_target_block(ir, action.get("target", {}))
        insert_paragraph_after(body, block, action.get("block", {}))
        return {"action": action_name, "block_id": block["id"]}
    if action_name in {"apply_style", "change_heading_level", "set_heading_level"}:
        block = find_target_block(ir, action.get("target", {}))
        style = action.get("style")
        if action_name != "apply_style":
            style = f"Heading{int(action.get('level'))}"
        apply_paragraph_style(body_child(body, block), str(style))
        return {"action": action_name, "block_id": block["id"], "style": style}
    if action_name == "update_caption":
        caption_block = find_caption_block(ir, action.get("target", {}))
        replace_paragraph_text(body_child(body, caption_block), str(action.get("caption") or action.get("value", "")))
        return {"action": action_name, "block_id": caption_block["id"]}
    if action_name == "delete_paragraph":
        block = find_target_block(ir, action.get("target", {}))
        child = body_child(body, block)
        body.remove(child)
        return {"action": action_name, "block_id": block["id"]}
    if action_name == "replace_section_text":
        return replace_section_text(body, ir, action.get("target", {}), action.get("value", ""))
    if action_name == "set_keywords":
        return set_keywords(body, ir, action.get("value", []))
    if action_name == "insert_section_after":
        return insert_section_after(body, ir, action)
    if action_name in {"cite_table", "cite_figure"}:
        return insert_citation_sentence(body, ir, action_name, action.get("target", {}), str(action.get("sentence", "")))
    raise ValueError(f"unsupported patch action: {action_name}")


def current_ir(package: DocxPackage, body: ET.Element) -> dict[str, Any]:
    styles = parse_styles(package)
    rels = package.document_relationships_by_id()
    blocks = parse_body_blocks(body, styles, rels)
    return {
        "blocks": blocks,
        "sections": detect_sections(blocks),
        "figures": detect_figures(blocks, rels),
        "tables": detect_tables(blocks),
    }


def load_patch(patch: dict[str, Any] | str | Path) -> dict[str, Any]:
    if isinstance(patch, dict):
        return patch
    path = Path(patch)
    text = path.read_text(encoding="utf-8")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    try:
        import yaml  # type: ignore

        data = yaml.safe_load(text)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return parse_simple_yaml_patch(text)


def parse_simple_yaml_patch(text: str) -> dict[str, Any]:
    """Parse the small patch subset documented in SKILL.md when PyYAML is unavailable."""
    lines = [line.rstrip("\n") for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#")]
    result: dict[str, Any] = {"actions": []}
    current_action: dict[str, Any] | None = None
    current_map_key: str | None = None
    index = 0
    while index < len(lines):
        raw = lines[index]
        stripped = raw.strip()
        if stripped.startswith("version:"):
            result["version"] = int(stripped.split(":", 1)[1].strip())
        elif stripped == "actions:":
            pass
        elif stripped.startswith("- "):
            current_action = {}
            result["actions"].append(current_action)
            key, value = parse_key_value(stripped[2:])
            current_action[key] = value
            current_map_key = None
        elif current_action is not None and stripped.endswith(":"):
            key = stripped[:-1]
            current_action[key] = {}
            current_map_key = key
        elif current_action is not None:
            key, value = parse_key_value(stripped)
            if value == "|":
                block_lines: list[str] = []
                index += 1
                while index < len(lines) and lines[index].startswith(" "):
                    block_lines.append(lines[index].strip())
                    index += 1
                index -= 1
                value = "\n".join(block_lines)
            if current_map_key and raw.startswith(" " * 4):
                current_action[current_map_key][key] = value
            else:
                current_action[key] = value
                current_map_key = None
        index += 1
    return result


def parse_key_value(text: str) -> tuple[str, Any]:
    key, value = text.split(":", 1)
    value = value.strip()
    if value.startswith('"') and value.endswith('"'):
        value = value[1:-1]
    elif value.isdigit():
        return key.strip(), int(value)
    return key.strip(), value


def find_target_block(ir: dict[str, Any], target: dict[str, Any]) -> dict[str, Any]:
    block_id = target.get("block_id") or target.get("paragraph_id")
    if block_id:
        for block in ir["blocks"]:
            if block["id"] == block_id:
                return block
        raise ValueError(f"block not found: {block_id}")
    text = target.get("text")
    if text:
        matches = [block for block in ir["blocks"] if block.get("text") == text]
        if len(matches) == 1:
            return matches[0]
        raise ValueError(f"text target matched {len(matches)} blocks: {text}")
    section_type = target.get("section_type") or target.get("section")
    if section_type:
        section = find_section(ir, section_type)
        if section:
            return find_target_block(ir, {"block_id": section["heading_id"]})
    raise ValueError(f"unsupported or missing target: {target}")


def find_section(ir: dict[str, Any], section_name: str) -> dict[str, Any] | None:
    wanted = normalize_label(section_name)
    aliases = {
        "intro": "introduction",
        "materials and methods": "methods",
        "methodology": "methods",
        "conclusions": "conclusion",
        "bibliography": "references",
    }
    wanted = aliases.get(wanted, wanted)
    for section in ir.get("sections", []):
        section_type = normalize_label(section.get("type", ""))
        section_title = normalize_label(section.get("title", ""))
        if wanted in {section_type, section_title, aliases.get(section_title, section_title)}:
            return section
    return None


def normalize_label(text: str) -> str:
    import re

    text = re.sub(r"^\s*[0-9IVXivx.、)\-]+\s*", "", str(text))
    return re.sub(r"\s+", " ", text.strip().lower())


def find_caption_block(ir: dict[str, Any], target: dict[str, Any]) -> dict[str, Any]:
    if "figure_index" in target:
        figure = ir["figures"][int(target["figure_index"]) - 1]
        return find_target_block(ir, {"block_id": figure["caption"]["paragraph_id"]})
    if "table_index" in target:
        table = ir["tables"][int(target["table_index"]) - 1]
        return find_target_block(ir, {"block_id": table["caption"]["paragraph_id"]})
    return find_target_block(ir, target)


def body_child(body: ET.Element, block: dict[str, Any]) -> ET.Element:
    index = int(block["location"]["body_index"]) - 1
    children = list(body)
    if index < 0 or index >= len(children):
        raise ValueError(f"body index out of range for {block['id']}")
    return children[index]


def replace_paragraph_text(paragraph: ET.Element, value: str) -> None:
    if paragraph.tag != w_tag("p"):
        raise ValueError("target block is not a paragraph")
    ppr = paragraph.find(w_tag("pPr"))
    for child in list(paragraph):
        if child is not ppr:
            paragraph.remove(child)
    run = ET.Element(w_tag("r"))
    text = ET.SubElement(run, w_tag("t"))
    if value.startswith(" ") or value.endswith(" "):
        text.attrib[qn("http://www.w3.org/XML/1998/namespace", "space")] = "preserve"
    text.text = value
    paragraph.append(run)


def insert_paragraph_after(body: ET.Element, block: dict[str, Any], new_block: dict[str, Any]) -> None:
    children = list(body)
    index = int(block["location"]["body_index"]) - 1
    paragraph = make_paragraph(str(new_block.get("text", "")), str(new_block.get("style", "Normal")))
    body.insert(index + 1, paragraph)


def make_paragraph(text_value: str, style: str) -> ET.Element:
    paragraph = ET.Element(w_tag("p"))
    ppr = ET.SubElement(paragraph, w_tag("pPr"))
    pstyle = ET.SubElement(ppr, w_tag("pStyle"))
    pstyle.attrib[qn("http://schemas.openxmlformats.org/wordprocessingml/2006/main", "val")] = style
    run = ET.SubElement(paragraph, w_tag("r"))
    text = ET.SubElement(run, w_tag("t"))
    text.text = text_value
    return paragraph


def replace_section_text(body: ET.Element, ir: dict[str, Any], target: dict[str, Any], value: Any) -> dict[str, Any]:
    section = find_section(ir, str(target.get("section") or target.get("section_type") or target.get("title") or ""))
    if not section:
        raise ValueError(f"section not found: {target}")
    values = normalize_paragraph_values(value)
    if not values:
        raise ValueError("replace_section_text requires non-empty value")
    paragraphs = editable_section_paragraphs(ir, section)
    if paragraphs:
        first = paragraphs[0]
        replace_paragraph_text(body_child(body, first), values[0])
        for old in reversed(paragraphs[1:]):
            body.remove(body_child(body, old))
        insert_after_block(body, first, values[1:], first.get("style", "Normal"))
        first_id = first["id"]
    else:
        heading = find_target_block(ir, {"block_id": section["heading_id"]})
        insert_after_block(body, heading, values, "Normal")
        first_id = heading["id"]
    return {"action": "replace_section_text", "section": section["title"], "block_id": first_id, "paragraph_count": len(values)}


def normalize_paragraph_values(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    if not text:
        return []
    return [item.strip() for item in text.split("\n\n") if item.strip()]


def editable_section_paragraphs(ir: dict[str, Any], section: dict[str, Any]) -> list[dict[str, Any]]:
    content = section_content_blocks(ir, section)
    return [
        block
        for block in content
        if block.get("type") == "paragraph"
        and block.get("text", "").strip()
        and not is_keyword_text(block.get("text", ""))
        and not is_caption_block(ir, block)
    ]


def section_content_blocks(ir: dict[str, Any], section: dict[str, Any]) -> list[dict[str, Any]]:
    blocks = ir.get("blocks", [])
    start = next((index for index, block in enumerate(blocks) if block.get("id") == section.get("heading_id")), None)
    if start is None:
        return []
    level = int(blocks[start].get("level", section.get("level", 1)))
    content = []
    for block in blocks[start + 1 :]:
        if block.get("type") == "heading" and int(block.get("level", 1)) <= level:
            break
        content.append(block)
    return content


def is_keyword_text(text: str) -> bool:
    import re

    return bool(re.match(KEYWORD_PREFIX_RE, text, re.I))


def is_caption_block(ir: dict[str, Any], block: dict[str, Any]) -> bool:
    block_id = block.get("id")
    for figure in ir.get("figures", []):
        if (figure.get("caption") or {}).get("paragraph_id") == block_id:
            return True
    for table in ir.get("tables", []):
        if (table.get("caption") or {}).get("paragraph_id") == block_id:
            return True
    return False


def insert_after_block(body: ET.Element, block: dict[str, Any], values: list[str], style: str) -> None:
    index = int(block["location"]["body_index"]) - 1
    for offset, text in enumerate(values, start=1):
        body.insert(index + offset, make_paragraph(text, style))


def set_keywords(body: ET.Element, ir: dict[str, Any], value: Any) -> dict[str, Any]:
    keywords = value if isinstance(value, list) else [item.strip() for item in str(value).split(";") if item.strip()]
    keyword_text = "Keywords: " + "; ".join(str(item).strip() for item in keywords if str(item).strip())
    for block in ir.get("blocks", []):
        if block.get("type") == "paragraph" and is_keyword_text(block.get("text", "")):
            replace_paragraph_text(body_child(body, block), keyword_text)
            return {"action": "set_keywords", "block_id": block["id"], "keyword_count": len(keywords)}
    section = find_section(ir, "abstract")
    if section:
        paragraphs = editable_section_paragraphs(ir, section)
        anchor = paragraphs[-1] if paragraphs else find_target_block(ir, {"block_id": section["heading_id"]})
    else:
        anchor = ir["blocks"][0]
    insert_after_block(body, anchor, [keyword_text], "Normal")
    return {"action": "set_keywords", "block_id": anchor["id"], "keyword_count": len(keywords)}


def insert_section_after(body: ET.Element, ir: dict[str, Any], action: dict[str, Any]) -> dict[str, Any]:
    target = action.get("target", {})
    section = find_section(ir, str(target.get("section") or target.get("section_type") or target.get("title") or ""))
    if not section:
        raise ValueError(f"section not found: {target}")
    insert_index = section_end_body_index(ir, section)
    level = int(action.get("level") or section.get("level") or 1)
    heading_style = f"Heading{level}"
    elements = [make_paragraph(str(action.get("heading", "New Section")), heading_style)]
    for paragraph in normalize_paragraph_values(action.get("paragraphs", [])):
        elements.append(make_paragraph(paragraph, "Normal"))
    for offset, element in enumerate(elements):
        body.insert(insert_index + offset, element)
    return {"action": "insert_section_after", "section": section["title"], "inserted_count": len(elements)}


def section_end_body_index(ir: dict[str, Any], section: dict[str, Any]) -> int:
    blocks = ir.get("blocks", [])
    start = next((index for index, block in enumerate(blocks) if block.get("id") == section.get("heading_id")), None)
    if start is None:
        raise ValueError(f"section start not found: {section}")
    level = int(blocks[start].get("level", section.get("level", 1)))
    end_body_index = int(blocks[start]["location"]["body_index"])
    for block in blocks[start + 1 :]:
        if block.get("type") == "heading" and int(block.get("level", 1)) <= level:
            return int(block["location"]["body_index"]) - 1
        end_body_index = int(block["location"]["body_index"])
    return end_body_index


def insert_citation_sentence(body: ET.Element, ir: dict[str, Any], action_name: str, target: dict[str, Any], sentence: str) -> dict[str, Any]:
    if not sentence.strip():
        raise ValueError(f"{action_name} requires sentence")
    section = find_section(ir, str(target.get("section") or target.get("section_type") or "results"))
    if not section:
        raise ValueError(f"section not found for citation: {target}")
    paragraphs = editable_section_paragraphs(ir, section)
    anchor = paragraphs[-1] if paragraphs else find_target_block(ir, {"block_id": section["heading_id"]})
    insert_after_block(body, anchor, [sentence.strip()], anchor.get("style", "Normal"))
    return {"action": action_name, "block_id": anchor["id"], "section": section["title"]}


def apply_paragraph_style(paragraph: ET.Element, style: str) -> None:
    if paragraph.tag != w_tag("p"):
        raise ValueError("target block is not a paragraph")
    ppr = paragraph.find(w_tag("pPr"))
    if ppr is None:
        ppr = ET.Element(w_tag("pPr"))
        paragraph.insert(0, ppr)
    pstyle = ppr.find(w_tag("pStyle"))
    if pstyle is None:
        pstyle = ET.SubElement(ppr, w_tag("pStyle"))
    pstyle.attrib[qn("http://schemas.openxmlformats.org/wordprocessingml/2006/main", "val")] = style
