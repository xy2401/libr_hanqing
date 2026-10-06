"""Inspect a publication-only source tree before packaging."""

from pathlib import Path
import re
from urllib.parse import unquote, urlsplit
import xml.etree.ElementTree as ET

from ..publication.xmlutil import NS, XHTML, OPS


def resolve_reference(root: Path, source: Path, value: str) -> tuple[Path | None, str]:
    url = urlsplit(value)
    if url.scheme or url.netloc:
        if url.scheme not in ("http", "https", "mailto", "data"):
            raise ValueError(f"Unsupported URL: {value}")
        return None, ""
    path = unquote(url.path)
    if "\\" in path or ":" in path or path.startswith("/"):
        raise ValueError(f"Invalid local reference: {value}")
    target = (source.parent / path).resolve() if path else source.resolve()
    if not target.is_relative_to(root.resolve()) or not target.is_file():
        raise ValueError(f"Missing or escaping local reference: {source.name}: {value}")
    return target, unquote(url.fragment)


def check_source(source_root: Path) -> dict:
    if source_root.is_symlink():
        raise ValueError("Publication source may not be a symlink")
    root = source_root.resolve()
    if not root.is_dir() or root.name != "src":
        raise ValueError("Publication input must be an explicit src directory.")
    files = []
    for path in root.rglob("*"):
        if path.is_symlink():
            raise ValueError(f"Symlink in publication tree: {path}")
        if path.is_file() and path.name != ".gitkeep":
            if path.suffix.lower() in (".md", ".toml", ".pdf", ".epub", ".jsonl") or set(path.relative_to(root).parts) & {"md", "editorial", "raw", "inbox", "work", "dist"}:
                raise ValueError(f"Non-publication file in src: {path}")
            files.append(path)
    if (root / "mimetype").read_bytes() != b"application/epub+zip":
        raise ValueError("mimetype must contain only application/epub+zip.")
    container = ET.parse(root / "META-INF/container.xml")
    rootfiles = container.findall(".//{urn:oasis:names:tc:opendocument:xmlns:container}rootfile")
    if len(rootfiles) != 1:
        raise ValueError("Expected exactly one OPF rootfile.")
    opf_path, _ = resolve_reference(root, root / "mimetype", rootfiles[0].get("full-path", ""))
    if opf_path is None:
        raise ValueError("OPF must be local.")
    opf = ET.parse(opf_path)
    items = opf.findall("opf:manifest/opf:item", NS)
    manifest = {}
    for item in items:
        identifier = item.get("id")
        if not identifier or identifier in manifest:
            raise ValueError("Missing or duplicate OPF manifest ID.")
        target, _ = resolve_reference(root, opf_path, item.get("href", ""))
        if target is None:
            raise ValueError("Remote publication resources are not supported.")
        manifest[identifier] = (target, item)
    resource_paths = {p for p, _ in manifest.values()}
    expected = {p.resolve() for p in files} - {opf_path, root / "mimetype", root / "META-INF/container.xml"}
    if resource_paths != expected:
        raise ValueError(f"OPF manifest does not match src resources: {sorted(str(p.relative_to(root)) for p in resource_paths ^ expected)}")
    spine = opf.findall("opf:spine/opf:itemref", NS)
    if not spine or len({n.get("idref") for n in spine}) != len(spine):
        raise ValueError("Missing spine or duplicate spine entry.")
    for itemref in spine:
        entry = manifest.get(itemref.get("idref"))
        if entry is None or entry[1].get("media-type") != "application/xhtml+xml":
            raise ValueError("Every spine entry must reference an XHTML resource.")
    nav_items = [p for p, item in manifest.values() if "nav" in item.get("properties", "").split()]
    if len(nav_items) != 1:
        raise ValueError("Expected one EPUB navigation document.")
    nav = ET.parse(nav_items[0])
    toc = nav.find(".//h:nav[@epub:type='toc']", NS)
    if toc is None or not toc.findall(".//h:a", NS):
        raise ValueError("Missing or empty navigation TOC.")
    spine_paths = {manifest[itemref.get("idref")][0] for itemref in spine}
    for link in nav.findall(".//h:a", NS):
        target, _ = resolve_reference(root, nav_items[0], link.get("href", ""))
        if target not in spine_paths:
            raise ValueError(f"Navigation target is not a spine item: {link.get('href')}")
    all_ids = set()
    document_ids = {}
    xml_docs = {}
    for path in files:
        if path.suffix in (".xhtml", ".svg", ".opf", ".xml"):
            document = ET.parse(path)
            ids = set()
            for node in document.iter():
                if node.get("id"):
                    identifier = node.get("id")
                    if identifier in all_ids:
                        raise ValueError(f"ID is not globally unique: {identifier}")
                    all_ids.add(identifier)
                    ids.add(identifier)
                if node.tag == f"{{{XHTML}}}script" or any(k.lower().startswith("on") for k in node.attrib):
                    raise ValueError("Scripting is not supported in this profile.")
            document_ids[path.resolve()] = ids
            xml_docs[path] = document
    links = 0
    for path, document in xml_docs.items():
        for node in document.iter():
            for key, value in node.attrib.items():
                if key.rsplit("}", 1)[-1] not in ("href", "src"):
                    continue
                target, fragment = resolve_reference(root, path, value)
                if target is not None and fragment and fragment not in document_ids.get(target, set()):
                    raise ValueError(f"Broken fragment: {path.name}: {value}")
                if target is None and node.tag != f"{{{XHTML}}}a" and not value.startswith("data:"):
                    raise ValueError("External publication media are not supported.")
                links += 1
    for path in files:
        if path.suffix == ".css":
            for value in re.findall(r"url\(['\"]?([^'\")]+)", path.read_text(encoding="utf-8")):
                resolve_reference(root, path, value)
    return {"status": "passed", "resources": len(items), "spine_items": len(spine), "globally_unique_ids": len(all_ids), "links": links, "nav_links": len(toc.findall('.//h:a', NS))}
