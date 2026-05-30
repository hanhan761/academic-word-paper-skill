from __future__ import annotations

import posixpath
import zipfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"

NS = {
    "w": W_NS,
    "r": R_NS,
    "a": A_NS,
    "rel": REL_NS,
}

ET.register_namespace("w", W_NS)
ET.register_namespace("r", R_NS)
ET.register_namespace("a", A_NS)


def qn(namespace: str, tag: str) -> str:
    return f"{{{namespace}}}{tag}"


def w_tag(tag: str) -> str:
    return qn(W_NS, tag)


def r_attr(name: str) -> str:
    return qn(R_NS, name)


def rel_attr(name: str) -> str:
    return name


class DocxPackage:
    """In-memory view of a docx zip package."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.parts: dict[str, bytes] = {}
        self.order: list[str] = []
        self._load()

    def _load(self) -> None:
        with zipfile.ZipFile(self.path, "r") as archive:
            self.order = archive.namelist()
            self.parts = {name: archive.read(name) for name in self.order}

    def has_part(self, name: str) -> bool:
        return name in self.parts

    def read_text(self, name: str) -> str:
        return self.parts[name].decode("utf-8")

    def parse_xml(self, name: str) -> ET.Element:
        return ET.fromstring(self.parts[name])

    def parse_xml_optional(self, name: str) -> ET.Element | None:
        if name not in self.parts:
            return None
        return self.parse_xml(name)

    def xml_part_names(self) -> list[str]:
        return [name for name in self.parts if name.endswith(".xml") or name.endswith(".rels")]

    def media_parts(self) -> list[str]:
        return sorted(name for name in self.parts if name.startswith("word/media/"))

    def relationships(self) -> list[dict[str, Any]]:
        rels: list[dict[str, Any]] = []
        for rels_name in self.parts:
            if not rels_name.endswith(".rels"):
                continue
            try:
                root = self.parse_xml(rels_name)
            except ET.ParseError:
                continue
            source_part = rels_source_part(rels_name)
            source_base = posixpath.dirname(source_part)
            for rel in root.findall(f"{{{REL_NS}}}Relationship"):
                target = rel.attrib.get("Target", "")
                mode = rel.attrib.get("TargetMode", "Internal")
                resolved = None
                if target and mode != "External":
                    if target.startswith("/"):
                        resolved = target.lstrip("/")
                    elif source_base:
                        resolved = posixpath.normpath(posixpath.join(source_base, target))
                    else:
                        resolved = posixpath.normpath(target)
                rels.append(
                    {
                        "id": rel.attrib.get("Id", ""),
                        "type": rel.attrib.get("Type", ""),
                        "target": target,
                        "target_mode": mode,
                        "source_rels": rels_name,
                        "source_part": source_part,
                        "resolved_target": resolved,
                    }
                )
        return rels

    def document_relationships_by_id(self) -> dict[str, dict[str, Any]]:
        return {
            rel["id"]: rel
            for rel in self.relationships()
            if rel["source_part"] == "word/document.xml" and rel["id"]
        }

    def missing_relationship_targets(self) -> list[dict[str, Any]]:
        missing = []
        for rel in self.relationships():
            target = rel.get("resolved_target")
            if target and target not in self.parts:
                missing.append(rel)
        return missing

    def write(self, out_path: str | Path, updates: dict[str, bytes]) -> None:
        out = Path(out_path)
        temp = out.with_name(f"{out.name}.tmpzip")
        names = list(self.order)
        for name in updates:
            if name not in self.parts and name not in names:
                names.append(name)
        with zipfile.ZipFile(temp, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name in names:
                data = updates.get(name, self.parts.get(name))
                if data is not None:
                    archive.writestr(name, data)
        temp.replace(out)


def rels_source_part(rels_name: str) -> str:
    if rels_name == "_rels/.rels":
        return ""
    directory, filename = posixpath.split(rels_name)
    if not directory.endswith("_rels") or not filename.endswith(".rels"):
        return ""
    parent = posixpath.dirname(directory)
    source_file = filename[: -len(".rels")]
    return posixpath.normpath(posixpath.join(parent, source_file))


def xml_bytes(root: ET.Element) -> bytes:
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def text_content(element: ET.Element) -> str:
    pieces: list[str] = []
    for node in element.iter():
        if node.tag in {w_tag("t"), w_tag("delText")} and node.text:
            pieces.append(node.text)
        elif node.tag == w_tag("tab"):
            pieces.append("\t")
        elif node.tag == w_tag("br"):
            pieces.append("\n")
    return "".join(pieces)
