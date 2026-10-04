"""创建新的出版源码骨架；绝不重新生成或覆盖已存在的书籍。"""

import json
from datetime import datetime, timezone
from html import escape
from importlib.resources import files
from pathlib import Path
from string import Template

from .models import BookMetadata, CREATOR_ROLE_CODES


def _quoted(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _metadata_toml(book: BookMetadata) -> str:
    lines = ["schema_version = 1"]
    for key in ("id", "work_id", "title", "language", "edition", "status"):
        lines.append(f"{key} = {_quoted(getattr(book, key))}")
    for creator in book.creators:
        lines.extend([
            "", "[[creators]]", f"id = {_quoted(creator.id)}",
            f"name = {_quoted(creator.name)}", f"role = {_quoted(creator.role)}",
        ])
    for series in book.series:
        lines.extend(["", "[[series]]", f"id = {_quoted(series.id)}", f"name = {_quoted(series.name)}"])
        if series.position is not None:
            lines.append(f"position = {series.position}")
    return "\n".join(lines) + "\n"


def initialize_book(root: Path, book: BookMetadata) -> Path:
    if book.status != "draft":
        raise ValueError("初始化只接受 draft")
    target = root.resolve() / "books" / book.id
    if target.exists():
        raise FileExistsError(f"书籍目录已存在，不会覆盖：{target}")

    creator_xml = []
    for index, creator in enumerate(book.creators, 1):
        element = "creator" if creator.role == "author" else "contributor"
        creator_xml.append(f'\t\t<dc:{element} id="creator-{index}">{escape(creator.name)}</dc:{element}>')
        creator_xml.append(
            f'\t\t<meta refines="#creator-{index}" property="role" scheme="marc:relators">'
            f'{CREATOR_ROLE_CODES[creator.role]}</meta>'
        )
    collection_xml = []
    for index, series in enumerate(book.series, 1):
        collection_xml.extend([
            f'\t\t<meta property="belongs-to-collection" id="series-{index}">{escape(series.name)}</meta>',
            f'\t\t<meta refines="#series-{index}" property="collection-type">series</meta>',
        ])
        if series.position is not None:
            collection_xml.append(f'\t\t<meta refines="#series-{index}" property="group-position">{series.position}</meta>')

    context = {
        "book_id": book.id,
        "title": escape(book.title),
        "language": escape(book.language),
        "edition": escape(book.edition),
        "author_names": escape("、".join(c.name for c in book.creators if c.role == "author") or "未署名"),
        "modified": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "creators": "\n".join(creator_xml),
        "collections": "\n".join(collection_xml),
    }
    resources = files("hanqing").joinpath("templates")
    template_targets = {
        "container.xml.tpl": "src/META-INF/container.xml",
        "content.opf.tpl": "src/epub/content.opf",
        "titlepage.xhtml.tpl": "src/epub/text/titlepage.xhtml",
        "colophon.xhtml.tpl": "src/epub/text/colophon.xhtml",
        "toc.xhtml.tpl": "src/epub/toc.xhtml",
    }
    output = {
        destination: Template(resources.joinpath(template).read_text(encoding="utf-8")).substitute(context)
        for template, destination in template_targets.items()
    }
    for stylesheet in ("core.css", "local.css"):
        output[f"src/epub/css/{stylesheet}"] = resources.joinpath(stylesheet).read_text(encoding="utf-8")
    output.update({
        "book.toml": _metadata_toml(book),
        "md/.gitkeep": "",
        "src/mimetype": "application/epub+zip",
        "images/.gitkeep": "",
        "src/epub/images/.gitkeep": "",
        "editorial/.gitkeep": "",
    })
    # 先完成所有内容生成，再排他地创建新目录；输入错误不留下半成品。
    target.parent.mkdir(parents=True, exist_ok=True)
    target.mkdir(exist_ok=False)
    for relative_path, content in output.items():
        destination = target / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
    return target
