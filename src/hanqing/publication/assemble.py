"""Create inspectable publication proposals, never replace a book's src/."""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET

from ..catalog import load_book
from ..models import validate_id, CREATOR_ROLE_CODES
from ..validators.publication import check_source
from .markdown import convert_markdown, select_markdown
from .xmlutil import DC, NS, OPF, OPS, XHTML, XML, html_document, project_path, write_xml


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree_hashes(directory: Path) -> dict[str, str]:
    if directory.is_symlink() or any(path.is_symlink() for path in directory.rglob("*")):
        raise ValueError("Source hashes may not follow symlinks")
    return {path.relative_to(directory).as_posix(): digest(path) for path in sorted(directory.rglob("*")) if path.is_file() and path.name != ".gitkeep"}


def read_context(root: Path, manifest: Path, book_id: str) -> tuple[dict, dict, Path]:
    root = root.resolve()
    manifest = manifest.resolve()
    if not manifest.is_relative_to(root / "data" / "work") or manifest.name != "manifest.json":
        raise ValueError("Use the source set's data/work/<id>/manifest.json")
    data = json.loads(manifest.read_text(encoding="utf-8"))
    if data.get("schema_version") != 3 or data.get("path_base") != "project":
        raise ValueError("Assembly requires manifest schema 3 with project-relative paths")
    validate_id(book_id)
    matches = [item for item in data["books"] if item["book_id"] == book_id]
    if len(matches) != 1:
        raise ValueError("Exactly one book relationship is required in the work manifest")
    relation = matches[0]
    directory = project_path(root, relation["book_directory"])
    if directory != root / "books" / book_id:
        raise ValueError("Book directory does not match its stable ID")
    return data, relation, directory


def save_manifest(path: Path, data: dict) -> None:
    temporary = path.with_suffix(".json.tmp")
    if temporary.exists():
        raise FileExistsError(temporary)
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    temporary.replace(path)


def markdown_directory(root: Path, manifest: Path, relation: dict, book: Path) -> Path:
    """Use the declared source-set working directory; support earlier book snapshots."""
    path = project_path(root, relation.get("markdown_directory", f"books/{book.name}/md"))
    if path != book / "md" and (path.parent != manifest.parent or not path.name.startswith("md.")):
        raise ValueError("Working Markdown must belong to this source set's md.<work>/ directory")
    return path


def working_editorial_directory(root: Path, manifest: Path, relation: dict, work_id: str) -> Path:
    value = relation.get("editorial_directory", (manifest.parent / f"editorial.{work_id}").relative_to(root).as_posix())
    path = project_path(root, value)
    if path.parent != manifest.parent or not path.name.startswith("editorial."):
        raise ValueError("Working editorial records must belong to this work source set")
    return path


def _snapshot_markdown(root: Path, source: Path, book: Path) -> dict[str, str]:
    """Copy accepted baselines into Git without deleting or overwriting working material."""
    if source.is_symlink() or any(p.is_symlink() for p in source.rglob("*")):
        raise ValueError("Markdown snapshots may not follow symlinks")
    copies = []
    for path in sorted(source.rglob("*.md")):
        if not path.is_file():
            continue
        target = project_path(root, (book / "md" / path.relative_to(source)).relative_to(root).as_posix())
        sha = digest(path)
        if target.exists() and (not target.is_file() or digest(target) != sha):
            raise FileExistsError(f"Existing book snapshot is preserved; review its update explicitly: {target}")
        copies.append((path, target, sha))
    for path, target, sha in copies:
        target.parent.mkdir(parents=True, exist_ok=True)
        if path != target and not target.exists():
            shutil.copy2(path, target)
        if digest(target) != sha:
            raise ValueError(f"Markdown snapshot SHA-256 mismatch: {target}")
    return {path.relative_to(root).as_posix(): target.relative_to(root).as_posix() for path, target, _ in copies}


def _frontmatter(epub: Path, book) -> None:
    cover, body = html_document("封面", book.language, "frontmatter")
    section = ET.SubElement(body, f"{{{XHTML}}}section", {"id": "cover-page", f"{{{OPS}}}type": "cover"})
    ET.SubElement(section, f"{{{XHTML}}}img", {"src": "../images/cover.svg", "alt": f"{book.title}，封面"})
    write_xml(epub / "text" / "cover.xhtml", cover)
    colophon, body = html_document("版本說明", book.language, "backmatter")
    section = ET.SubElement(body, f"{{{XHTML}}}section", {"id": "colophon", f"{{{OPS}}}type": "colophon"})
    ET.SubElement(section, f"{{{XHTML}}}h2").text = "版本說明"
    ET.SubElement(section, f"{{{XHTML}}}p").text = book.edition
    write_xml(epub / "text" / "colophon.xhtml", colophon)


def _navigation(epub: Path, book, chapters: list[dict]) -> int:
    nav, body = html_document("目錄", book.language, "frontmatter")
    # The nav document sits one level above text/.
    for link in nav.findall("h:head/h:link", NS):
        link.set("href", link.get("href")[3:])
    toc = ET.SubElement(body, f"{{{XHTML}}}nav", {"id": "navigation-toc", f"{{{OPS}}}type": "toc"})
    ET.SubElement(toc, f"{{{XHTML}}}h1").text = "目錄"
    ordered = ET.SubElement(toc, f"{{{XHTML}}}ol")
    count = 0
    for chapter in chapters:
        li = ET.SubElement(ordered, f"{{{XHTML}}}li")
        ET.SubElement(li, f"{{{XHTML}}}a", {"href": f"text/{chapter['chapter_id']}.xhtml#{chapter['chapter_id']}"}).text = chapter["title"]
        count += 1
        if chapter["navigation"]:
            children = ET.SubElement(li, f"{{{XHTML}}}ol")
            for anchor, title in chapter["navigation"]:
                child = ET.SubElement(children, f"{{{XHTML}}}li")
                ET.SubElement(child, f"{{{XHTML}}}a", {"href": f"text/{chapter['chapter_id']}.xhtml#{anchor}"}).text = title
                count += 1
    landmarks = ET.SubElement(body, f"{{{XHTML}}}nav", {
        "id": "navigation-landmarks", f"{{{OPS}}}type": "landmarks", "hidden": "hidden",
    })
    ET.SubElement(landmarks, f"{{{XHTML}}}h2").text = "導覽"
    ordered = ET.SubElement(landmarks, f"{{{XHTML}}}ol")
    first_body = next((ch for ch in chapters if ch["epub_type"] == "chapter"), chapters[0])
    for href, label, kind in [
        ("text/cover.xhtml#cover-page", "封面", "cover"),
        ("text/titlepage.xhtml#titlepage", "書名頁", "titlepage"),
        ("toc.xhtml#navigation-toc", "目錄", "toc"),
        (f"text/{first_body['chapter_id']}.xhtml#{first_body['chapter_id']}", "正文", "bodymatter"),
    ]:
        li = ET.SubElement(ordered, f"{{{XHTML}}}li")
        ET.SubElement(li, f"{{{XHTML}}}a", {"href": href, f"{{{OPS}}}type": kind}).text = label
    write_xml(epub / "toc.xhtml", nav)
    return count


def _package_document(epub: Path, book, chapters: list[dict], modified: str) -> None:
    package = ET.Element(f"{{{OPF}}}package", {
        "version": "3.0", "unique-identifier": "metadata-book-id", f"{{{XML}}}lang": book.language,
    })
    metadata = ET.SubElement(package, f"{{{OPF}}}metadata")
    ET.SubElement(metadata, f"{{{DC}}}identifier", {"id": "metadata-book-id"}).text = f"urn:hanqing:book:{book.id}"
    ET.SubElement(metadata, f"{{{DC}}}title").text = book.title
    ET.SubElement(metadata, f"{{{DC}}}language").text = book.language
    for index, creator in enumerate(book.creators, 1):
        identifier = f"metadata-creator-{index}"
        element = "creator" if creator.role == "author" else "contributor"
        ET.SubElement(metadata, f"{{{DC}}}{element}", {"id": identifier}).text = creator.name
        ET.SubElement(metadata, f"{{{OPF}}}meta", {
            "refines": f"#{identifier}", "property": "role", "scheme": "marc:relators",
        }).text = CREATOR_ROLE_CODES[creator.role]
    for index, series in enumerate(book.series, 1):
        identifier = f"metadata-series-{index}"
        ET.SubElement(metadata, f"{{{OPF}}}meta", {"property": "belongs-to-collection", "id": identifier}).text = series.name
        ET.SubElement(metadata, f"{{{OPF}}}meta", {"refines": f"#{identifier}", "property": "collection-type"}).text = "series"
        if series.position is not None:
            ET.SubElement(metadata, f"{{{OPF}}}meta", {"refines": f"#{identifier}", "property": "group-position"}).text = str(series.position)
    ET.SubElement(metadata, f"{{{OPF}}}meta", {"property": "dcterms:modified"}).text = modified
    manifest = ET.SubElement(package, f"{{{OPF}}}manifest")
    types = {".xhtml": "application/xhtml+xml", ".css": "text/css", ".svg": "image/svg+xml", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}
    ids = {}
    for index, path in enumerate(sorted(epub.rglob("*")), 1):
        if not path.is_file() or path.name == "content.opf":
            continue
        href = path.relative_to(epub).as_posix()
        identifier = f"resource-{index}"
        ids[href] = identifier
        attrs = {"id": identifier, "href": href, "media-type": types[path.suffix]}
        properties = []
        if href == "toc.xhtml":
            properties.append("nav")
        if href == "images/cover.svg":
            properties.append("cover-image")
        if path.suffix == ".xhtml" and ET.parse(path).getroot().find(".//{http://www.w3.org/2000/svg}svg") is not None:
            properties.append("svg")
        if properties:
            attrs["properties"] = " ".join(properties)
        ET.SubElement(manifest, f"{{{OPF}}}item", attrs)
    spine = ET.SubElement(package, f"{{{OPF}}}spine")
    for href in ["text/cover.xhtml", "text/titlepage.xhtml", "toc.xhtml", *[f"text/{c['chapter_id']}.xhtml" for c in chapters], "text/colophon.xhtml"]:
        attrs = {"idref": ids[href]}
        if href == "toc.xhtml":
            attrs["linear"] = "no"
        ET.SubElement(spine, f"{{{OPF}}}itemref", attrs)
    write_xml(epub / "content.opf", package)


def assemble_book(root: Path, manifest: Path, book_id: str, *, pandoc: str = "pandoc") -> dict:
    root = root.resolve()
    manifest = manifest.resolve()
    data, relation, book_directory = read_context(root, manifest, book_id)
    working_md = markdown_directory(root, manifest, relation, book_directory)
    book = load_book(book_directory / "book.toml")
    working_editorial = working_editorial_directory(root, manifest, relation, book.work_id)
    plan = relation.get("publication_plan", [])
    if not plan or len({p["chapter_id"] for p in plan}) != len(plan):
        raise ValueError("An explicit, ordered publication_plan with unique chapter IDs is required")
    allowed = {entry["path"] for entry in relation["markdown_order"]}
    records = {item["path"]: item for item in data["files"]}
    target = manifest.parent / f"proposal.{book_id}"
    if target.exists():
        raise FileExistsError(f"Existing proposal is preserved: {target}")
    selections = []
    for selection in plan:
        validate_id(selection["chapter_id"])
        if selection["markdown_path"] not in allowed:
            raise ValueError("Publication plan must select an explicitly ordered Markdown baseline")
        path = project_path(root, selection["markdown_path"])
        if not path.is_relative_to(working_md) or path.suffix != ".md" or path.name.endswith(".original.md"):
            raise ValueError("Select working Markdown inside the declared markdown_directory")
        actual = digest(path)
        if actual != records[path.relative_to(root).as_posix()]["sha256"] or actual != selection["markdown_sha256"]:
            raise ValueError(f"Baseline SHA-256 changed: {path}")
        selected, decision = select_markdown(path.read_text(encoding="utf-8"), selection)
        selections.append((selection, selected, decision))
    version = subprocess.run([pandoc, "--version"], capture_output=True, encoding="utf-8", check=True, timeout=30).stdout.splitlines()[0]
    modified = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    temporary = Path(tempfile.mkdtemp(prefix=f".proposal.{book_id}.", dir=manifest.parent))
    try:
        original_src = book_directory / "src"
        if any(path.is_symlink() for path in original_src.rglob("*")):
            raise ValueError("Publication source must not contain symlinks")
        shutil.copytree(original_src, temporary / "src", ignore=shutil.ignore_patterns(".gitkeep"))
        base_source = tree_hashes(original_src)
        epub = temporary / "src" / "epub"
        chapters, mappings = [], []
        for selection, selected, decision in selections:
            chapter_id = selection["chapter_id"]
            path = epub / "text" / f"{chapter_id}.xhtml"
            # This is an isolated copy: regenerating it never changes canonical src/.
            fragment, chapter_map = convert_markdown(selected, chapter_id, pandoc=pandoc)
            kind = selection["epub_type"]
            if kind not in {"chapter", "preface"}:
                raise ValueError("Supported publication types: chapter, preface")
            html, body = html_document(selection["title"], book.language, "frontmatter" if kind == "preface" else "bodymatter")
            section = ET.SubElement(body, f"{{{XHTML}}}section", {"id": chapter_id, f"{{{OPS}}}type": kind})
            section.text = fragment.text
            section.extend(fragment)
            navigation = []
            for node in section.iter():
                tag = node.tag.rsplit("}", 1)[-1]
                text = "".join(node.itertext()).strip()
                paragraph_number = re.match(r"^§\s*(\d+)\b", text)
                if paragraph_number and tag in {"p", "h2", "h3", "h4", "h5", "h6"}:
                    navigation.append((node.get("id"), "§" + paragraph_number[1]))
                elif tag in {"h2", "h3"}:
                    navigation.append((node.get("id"), text))
            write_xml(path, html)
            for mapping in chapter_map:
                mappings.append({**mapping, "xhtml_path": f"src/epub/text/{chapter_id}.xhtml", "markdown_path": selection["markdown_path"], "markdown_sha256": selection["markdown_sha256"]})
            chapters.append({**selection, **decision, "navigation": navigation, "mapped_blocks": len(chapter_map)})
        _frontmatter(epub, book)
        nav_count = _navigation(epub, book, chapters)
        _package_document(epub, book, chapters, modified)
        structure = check_source(temporary / "src")
        (temporary / "source-map.jsonl").write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in mappings), encoding="utf-8", newline="\n")
        report = {"book_id": book_id, "status": "proposal", "human_acceptance": "pending", "created_at": modified, "pandoc": version, "reader": "commonmark_x; smart punctuation disabled", "chapters": chapters, "mapped_blocks": len(mappings), "navigation_entries": nav_count, "structure": structure, "publication_policy": relation["publication_policy"], "base_source_files": base_source, "proposal_source_files": tree_hashes(temporary / "src")}
        (temporary / "assembly-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
        temporary.rename(target)
    finally:
        if temporary.exists() and temporary.parent == manifest.parent and temporary.name.startswith(f".proposal.{book_id}."):
            shutil.rmtree(temporary)
    working_editorial.mkdir(exist_ok=True)
    for name, content in {
        "review.toml": 'schema_version = 1\nstatus = "pending"\nreviewer = ""\nreviewed_at = ""\n',
        "decisions.jsonl": "",
        "notes.md": "# 整理记录\n\n在 work 保存校勘政策、疑点和处理记录；具体成品完成整理后逐项确认。\n",
    }.items():
        path = working_editorial / name
        if not path.exists():
            path.write_text(content, encoding="utf-8", newline="\n")
            data["files"].append({"path": path.relative_to(root).as_posix(), "kind": "project-record",
                                  "book_id": book_id, "sha256": digest(path), "bytes": path.stat().st_size})
    relation["editorial_directory"] = working_editorial.relative_to(root).as_posix()
    data.setdefault("assembly_runs", []).append({
        "book_id": book_id, "created_at": modified, "status": "proposal", "pandoc": version,
        "proposal_directory": target.relative_to(root).as_posix(), "report_path": (target / "assembly-report.json").relative_to(root).as_posix(),
        "source_map_path": (target / "source-map.jsonl").relative_to(root).as_posix(), "baseline_sha256": {s["markdown_path"]: s["markdown_sha256"] for s, _, _ in selections},
        "human_acceptance": "pending",
    })
    save_manifest(manifest, data)
    return {"book_id": book_id, "proposal": str(target), "chapters": len(chapters), "mapped_blocks": len(mappings), "structure": structure, "human_acceptance": "pending"}


def accept_proposal(root: Path, manifest: Path, book_id: str, *, reviewer: str) -> dict:
    """Install an explicitly reviewed proposal, preserving the previous source tree.

    This accepts conversion structure only; it never marks proofreading complete.
    Subsequent accepted source must be edited through reviewed differences.
    """
    if not reviewer.strip():
        raise ValueError("An explicit human reviewer is required")
    root, manifest = root.resolve(), manifest.resolve()
    data, relation, directory = read_context(root, manifest, book_id)
    proposal = manifest.parent / f"proposal.{book_id}"
    report = json.loads((proposal / "assembly-report.json").read_text(encoding="utf-8"))
    if report.get("book_id") != book_id or report.get("human_acceptance") != "pending":
        raise ValueError("Proposal is not pending acceptance for this book")
    if tree_hashes(directory / "src") != report.get("base_source_files"):
        raise ValueError("Publication source changed since proposal generation; review the differences")
    if tree_hashes(proposal / "src") != report.get("proposal_source_files"):
        raise ValueError("Proposal source changed since the recorded structure check")
    if (directory / "editorial" / "conversion-review.json").exists():
        raise ValueError("Already accepted conversion is preserved; use reviewed differences")
    if (directory / "editorial" / "source-map.jsonl").exists() and (directory / "editorial" / "source-map.jsonl").stat().st_size:
        raise FileExistsError(directory / "editorial" / "source-map.jsonl")
    for chapter in report["chapters"]:
        if digest(project_path(root, chapter["markdown_path"])) != chapter["markdown_sha256"]:
            raise ValueError("Markdown baseline changed since proposal generation")
    check_source(proposal / "src")
    previous = proposal / "previous-src"
    if previous.exists():
        raise FileExistsError(previous)
    snapshots = _snapshot_markdown(root, markdown_directory(root, manifest, relation, directory), directory)
    shutil.copytree(directory / "src", previous)
    # Only the exact proposal resources are installed, including regenerated OPF/nav.
    # No files from md/ or work are copied into publication src/.
    shutil.copytree(proposal / "src", directory / "src", dirs_exist_ok=True)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    rows = []
    for line in (proposal / "source-map.jsonl").read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        row["markdown_path"] = snapshots[row["markdown_path"]]
        row["xhtml_path"] = directory.relative_to(root).as_posix() + "/" + row["xhtml_path"]
        rows.append(row)
    editorial = directory / "editorial"
    editorial.mkdir(exist_ok=True)
    mapping = editorial / "source-map.jsonl"
    mapping.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8", newline="\n")
    accepted = {
        "book_id": book_id, "status": "conversion-accepted", "reviewer": reviewer, "accepted_at": now,
        "scope": "本轮正文结构及注释取舍；不等于文字疑点解决、影像校勘或发行验收。",
        "note_policy": relation["publication_policy"].get("note_scope", "explicit-publication-plan"),
        "pandoc": report["pandoc"], "chapters": [{**{key: c[key] for key in ("chapter_id", "title", "markdown_sha256", "line_range", "epub_type")}, "markdown_path": snapshots[c["markdown_path"]]} for c in report["chapters"]],
        "mapped_blocks": len(rows), "source_files": report["proposal_source_files"], "proofreading_status": "pending", "release_status": "not-released",
    }
    (editorial / "conversion-review.json").write_text(json.dumps(accepted, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    report.update(human_acceptance="accepted-conversion-only", accepted_at=now, reviewer=reviewer, previous_source_directory=previous.relative_to(root).as_posix())
    (proposal / "assembly-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    for run in data["assembly_runs"]:
        if run["proposal_directory"] == proposal.relative_to(root).as_posix():
            run.update(human_acceptance="accepted-conversion-only", accepted_at=now, reviewer=reviewer, accepted_source_files=report["proposal_source_files"])
    relation["markdown_snapshot_directory"] = (directory / "md").relative_to(root).as_posix()
    data.setdefault("baseline_snapshots", []).append({"book_id": book_id, "recorded_at": now, "reviewer": reviewer,
        "files": [{"working_path": path, "snapshot_path": target, "sha256": digest(project_path(root, target))} for path, target in snapshots.items()]})
    save_manifest(manifest, data)
    return {"book_id": book_id, "status": "conversion-accepted", "source": str(directory / "src"), "mapped_blocks": len(rows), "proofreading_status": "pending"}
