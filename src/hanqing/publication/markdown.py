"""Local Pandoc conversion with explicit selections and Markdown line mapping.

No OCR, spelling modernization, smart punctuation or remote model calls.
"""

import json
from html.parser import HTMLParser
import re
import subprocess
import xml.etree.ElementTree as ET

from .xmlutil import OPS, XHTML, XML

READER = "commonmark_x+sourcepos-smart-emoji-tex_math_dollars-yaml_metadata_block"
VOID = {"br", "hr", "img", "input", "source", "wbr", "area", "base", "col", "embed", "link", "meta", "param", "track"}
BLOCKS = {"p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "table", "blockquote", "pre", "dt", "dd"}


class FragmentParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = ET.Element(f"{{{XHTML}}}div")
        self.stack = [self.root]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "script" or any(name.startswith("on") for name, _ in attrs):
            raise ValueError("Active HTML is not permitted in publication text")
        node = ET.SubElement(self.stack[-1], f"{{{XHTML}}}{tag}", {
            name: value or "" for name, value in attrs
        })
        if tag not in VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        if tag in VOID:
            return
        if len(self.stack) == 1 or self.stack[-1].tag != f"{{{XHTML}}}{tag}":
            raise ValueError(f"Unbalanced HTML: {tag}")
        self.stack.pop()

    def handle_data(self, data: str) -> None:
        parent = self.stack[-1]
        if len(parent):
            parent[-1].tail = (parent[-1].tail or "") + data
        else:
            parent.text = (parent.text or "") + data


def select_markdown(text: str, selection: dict) -> tuple[str, dict]:
    """Keep original line numbers; drop only explicitly selected note callouts."""
    lines = text.splitlines()
    start, end = selection["line_range"]
    if type(start) is not int or type(end) is not int or not 1 <= start <= end <= len(lines):
        raise ValueError("Selection line range is outside the Markdown file")
    note_ids = selection.get("omit_note_ids", [])
    if len(set(note_ids)) != len(note_ids):
        raise ValueError("Duplicate omitted note ID")
    available = set(re.findall(r"^\[\^([^\]]+)\]:", text, re.M))
    if set(note_ids) - available:
        raise ValueError("Omitted note has no definition in the baseline")
    selected = [line if start <= index <= end else "" for index, line in enumerate(lines, 1)]
    removed = {}
    for note_id in note_ids:
        pattern = re.compile(r"\[\^" + re.escape(note_id) + r"\]")
        count = 0
        for index, line in enumerate(selected):
            selected[index], found = pattern.subn("", line)
            count += found
        removed[note_id] = count
    # Unresolved references must not silently become literal text or disappear.
    result = "\n".join(selected) + "\n"
    refs = set(re.findall(r"\[\^([^\]]+)\](?!:)", result))
    defs = set(re.findall(r"^\[\^([^\]]+)\]:", result, re.M))
    if refs - defs:
        raise ValueError(f"Unresolved retained notes: {sorted(refs - defs)}")
    return result, {"line_range": [start, end], "removed_note_callouts": removed}


def _positions(value: str) -> list[tuple[int, int]]:
    result = []
    for start, end, col in re.findall(r"(\d+):\d+-(\d+):(\d+)", value):
        first, last = int(start), int(end) - (int(col) == 1)
        result.append((first, max(first, last)))
    return result


def _unwrap(parent: ET.Element) -> None:
    for node in list(parent):
        _unwrap(node)
        if node.tag.rsplit("}", 1)[-1] not in {"div", "span"} or (node.get("wrapper") or node.get("data-wrapper")) != "1":
            continue
        index = list(parent).index(node)
        previous = parent[index - 1] if index else None
        if previous is None:
            parent.text = (parent.text or "") + (node.text or "")
        else:
            previous.tail = (previous.tail or "") + (node.text or "")
        children = list(node)
        for offset, child in enumerate(children):
            parent.insert(index + offset, child)
        tail_target = children[-1] if children else previous
        if tail_target is None:
            parent.text = (parent.text or "") + (node.tail or "")
        else:
            tail_target.tail = (tail_target.tail or "") + (node.tail or "")
        parent.remove(node)


def mark_english(parent: ET.Element) -> None:
    """Mark visible Latin words without changing any character or whitespace."""
    pattern = re.compile(r"[A-Za-z]+(?:[ \t]+[A-Za-z]+)*")
    original = list(parent)
    for child in original:
        mark_english(child)

    def insert_words(value: str, index: int, previous: ET.Element | None) -> None:
        matches = list(pattern.finditer(value))
        if not matches:
            return
        prefix = value[:matches[0].start()]
        if previous is None:
            parent.text = prefix
        else:
            previous.tail = prefix
        for offset, match in enumerate(matches):
            span = ET.Element(f"{{{XHTML}}}span", {"lang": "en", f"{{{XML}}}lang": "en"})
            span.text = match[0]
            end = matches[offset + 1].start() if offset + 1 < len(matches) else len(value)
            span.tail = value[match.end():end]
            parent.insert(index + offset, span)

    insert_words(parent.text or "", 0, None)
    for child in original:
        insert_words(child.tail or "", list(parent).index(child) + 1, child)


def convert_markdown(text: str, chapter_id: str, *, pandoc: str = "pandoc") -> tuple[ET.Element, list[dict]]:
    """Return selectable XHTML plus stable block IDs and baseline line ranges."""
    parsed = subprocess.run(
        [pandoc, "-f", READER, "-t", "json"], input=text, capture_output=True,
        encoding="utf-8", check=True, timeout=60,
    )
    ast = json.loads(parsed.stdout)
    headings = [block for block in ast["blocks"] if block["t"] == "Header"]
    if not headings:
        raise ValueError("Each selected chapter needs an explicit heading")
    shift = headings[0]["c"][0] - 1
    if shift:
        def lower(value):
            if isinstance(value, dict):
                if value.get("t") == "Header":
                    value["c"][0] = max(1, value["c"][0] - shift)
                for child in value.values():
                    lower(child)
            elif isinstance(value, list):
                for child in value:
                    lower(child)
        lower(ast["blocks"])
    written = subprocess.run(
        [pandoc, "-f", "json", "-t", "html5", "--wrap=none"],
        input=json.dumps(ast), capture_output=True, encoding="utf-8", check=True, timeout=60,
    )
    parser = FragmentParser()
    parser.feed(written.stdout)
    parser.close()
    if len(parser.stack) != 1:
        raise ValueError("Unclosed HTML from converter")
    fragment = parser.root
    parents = {child: parent for parent in fragment.iter() for child in parent}
    mappings = []
    id_map = {}
    for node in fragment.iter():
        tag = node.tag.rsplit("}", 1)[-1]
        if tag not in BLOCKS and "id" not in node.attrib:
            continue
        identifier = f"{chapter_id}-b{len(mappings) + 1:04}"
        if old := node.get("id"):
            if old in id_map:
                raise ValueError(f"Duplicate converter ID: {old}")
            id_map[old] = identifier
        node.set("id", identifier)
        positions = _positions(node.get("data-pos", ""))
        if not positions:
            positions = [p for child in node.iter() for p in _positions(child.get("data-pos", ""))]
        ancestor = node
        while not positions and ancestor in parents:
            ancestor = parents[ancestor]
            positions = _positions(ancestor.get("data-pos", ""))
        if not positions:
            raise ValueError(f"Cannot map {tag} to the Markdown baseline")
        mappings.append({
            "element_id": identifier, "element": tag,
            "markdown_lines": [min(p[0] for p in positions), max(p[1] for p in positions)],
        })
    for node in fragment.iter():
        if (href := node.get("href", "")).startswith("#"):
            if href[1:] not in id_map:
                raise ValueError(f"Unresolved generated anchor: {href}")
            node.set("href", "#" + id_map[href[1:]])
        if node.get("role") == "doc-noteref":
            node.set(f"{{{OPS}}}type", "noteref")
        if node.get("role") == "doc-endnotes":
            node.set(f"{{{OPS}}}type", "endnotes")
        if node.tag == f"{{{XHTML}}}li" and node.get("id") in {
            id_map[key] for key in id_map if key.startswith("fn") and not key.startswith("fnref")
        }:
            node.set(f"{{{OPS}}}type", "footnote")
        if node.tag == f"{{{XHTML}}}th":
            node.set("scope", "col")
    _unwrap(fragment)
    for node in fragment.iter():
        node.attrib.pop("data-pos", None)
        node.attrib.pop("wrapper", None)
        node.attrib.pop("data-wrapper", None)
    mark_english(fragment)
    return fragment, mappings
