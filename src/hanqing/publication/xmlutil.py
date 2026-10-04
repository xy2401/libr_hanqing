"""Shared EPUB XML vocabulary and UTF-8 serialization."""

from pathlib import Path
import xml.etree.ElementTree as ET

XHTML = "http://www.w3.org/1999/xhtml"
OPS = "http://www.idpf.org/2007/ops"
OPF = "http://www.idpf.org/2007/opf"
DC = "http://purl.org/dc/elements/1.1/"
XML = "http://www.w3.org/XML/1998/namespace"
NS = {"h": XHTML, "epub": OPS, "opf": OPF, "dc": DC}


def html_document(title: str, language: str, matter: str = "bodymatter") -> tuple[ET.Element, ET.Element]:
    html = ET.Element(f"{{{XHTML}}}html", {f"{{{XML}}}lang": language, "lang": language})
    head = ET.SubElement(html, f"{{{XHTML}}}head")
    ET.SubElement(head, f"{{{XHTML}}}title").text = title
    for name in ("core", "local"):
        ET.SubElement(head, f"{{{XHTML}}}link", {
            "href": f"../css/{name}.css", "rel": "stylesheet", "type": "text/css",
        })
    body = ET.SubElement(html, f"{{{XHTML}}}body", {f"{{{OPS}}}type": matter})
    return html, body


def write_xml(path: Path, root: ET.Element) -> None:
    ET.register_namespace("", XHTML if root.tag == f"{{{XHTML}}}html" else OPF)
    ET.register_namespace("epub", OPS)
    ET.register_namespace("dc", DC)
    content = ET.tostring(root, encoding="unicode")
    doctype = "<!DOCTYPE html>\n" if root.tag == f"{{{XHTML}}}html" else ""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('<?xml version="1.0" encoding="utf-8"?>\n' + doctype + content + "\n", encoding="utf-8", newline="\n")


def project_path(root: Path, value: str) -> Path:
    """Accept only project-relative POSIX paths without traversal or symlinks."""
    root = root.resolve()
    parts = value.split("/")
    if not value or "\\" in value or ":" in value or any(p in ("", ".", "..") for p in parts):
        raise ValueError(f"Invalid project-relative path: {value}")
    result = root.joinpath(*parts)
    if not result.resolve().is_relative_to(root.resolve()):
        raise ValueError(f"Path leaves project: {value}")
    cursor = result
    while cursor != root:
        if cursor.is_symlink():
            raise ValueError(f"Symlink is not permitted: {value}")
        cursor = cursor.parent
    return result
