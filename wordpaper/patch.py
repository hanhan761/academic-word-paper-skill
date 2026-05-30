from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from .ir import export_ir
from .ooxml import DocxPackage, qn, w_tag, xml_bytes


def apply_patch(input_docx: str | Path, patch: dict[str, Any] | str | Path, out_docx: str | Path) -> dict[str, Any]:
    patch_data = load_patch(patch)
    package = DocxPackage(input_docx)
    document = package.parse_xml("word/document.xml")
    body = document.find(f".//{w_tag('body')}")
    if body is None:
        return {"status": "error", "applied": [], "errors": [{"message": "word/document.xml has no body"}]}

    ir = export_ir(input_docx)
    applied: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for action in patch_data.get("actions", []):
        try:
            applied.append(apply_action(action, body, ir))
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
    raise ValueError(f"unsupported patch action: {action_name}")


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
    section_type = target.get("section_type")
    if section_type == "abstract":
        for section in ir.get("sections", []):
            if section.get("type") == "abstract":
                return find_target_block(ir, {"block_id": section["heading_id"]})
    raise ValueError(f"unsupported or missing target: {target}")


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
