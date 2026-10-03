"""离线书目 CLI。识别和构建阶段尚未接入。"""

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from .catalog import discover_books, load_book
from .models import BookMetadata, Creator, Series, validate_id
from .pipeline import STAGES
from .scaffold import initialize_book


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="hanqing", description="古籍数字化：书目管理与出版源码骨架")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="项目根目录（默认当前目录）")
    commands = parser.add_subparsers(dest="command", required=True)

    init = commands.add_parser("init-book", help="新建书目和 EPUB 出版源码目录")
    init.add_argument("id", help="带作者或系列前缀的数字版本 ID，例如 yan-fu-zhengzhi-jiangyi")
    init.add_argument("--work-id", required=True, help="作品 ID，例如 lunyu")
    init.add_argument("--title", required=True)
    init.add_argument("--author", help="作者显示名；与 --author-id 一同填写")
    init.add_argument("--author-id")
    init.add_argument("--series", help="系列显示名；与 --series-id 一同填写")
    init.add_argument("--series-id")
    init.add_argument("--series-position", type=int)
    init.add_argument("--language", default="zh-Hant")
    init.add_argument("--edition", default="古籍数字整理本")

    catalog = commands.add_parser("catalog", help="按作者或系列浏览书目")
    catalog.add_argument("--group-by", choices=("author", "series"))
    catalog.add_argument("--author", help="筛选作者 ID")
    catalog.add_argument("--series", help="筛选系列 ID")
    catalog.add_argument("--json", action="store_true", help="输出完整元数据；分组仅影响文本视图")

    commands.add_parser("check-catalog", help="验证书目元数据；不验证正文或 EPUB 合规性")
    plan = commands.add_parser("plan", help="显示尚待实现的处理阶段契约，不执行处理")
    plan.add_argument("id", help="书籍 ID")
    return parser


def _initialize(args: argparse.Namespace) -> None:
    if bool(args.author) != bool(args.author_id):
        raise ValueError("--author 和 --author-id 必须一同填写")
    if bool(args.series) != bool(args.series_id):
        raise ValueError("--series 和 --series-id 必须一同填写")
    if args.series_position is not None and not args.series:
        raise ValueError("--series-position 需要系列信息")
    book = BookMetadata(
        schema_version=1, id=args.id, work_id=args.work_id,
        title=args.title, language=args.language, edition=args.edition, status="draft",
        creators=(Creator(args.author_id, args.author),) if args.author else (),
        series=(Series(args.series_id, args.series, args.series_position),) if args.series else (),
    )
    target = initialize_book(args.root, book)
    print(f"已创建：{target}")
    print("状态：draft；请在 raw 清单登记来源并添加校勘正文。")


def _catalog(args: argparse.Namespace) -> None:
    books = discover_books(args.root)
    if args.author:
        validate_id(args.author)
        books = [book for book in books if any(c.id == args.author and c.role == "author" for c in book.creators)]
    if args.series:
        validate_id(args.series)
        books = [book for book in books if any(s.id == args.series for s in book.series)]
    if args.json:
        print(json.dumps([asdict(book) for book in books], ensure_ascii=False, indent=2))
        return
    if not books:
        print("暂无匹配书目。")
        return

    groups: dict[str, tuple[str, list[BookMetadata]]] = {}
    for book in books:
        if args.group_by == "author":
            labels = [(c.id, c.name) for c in book.creators if c.role == "author"] or [("", "未署名")]
        elif args.group_by == "series":
            labels = [(s.id, s.name) for s in book.series] or [("", "未归入系列")]
        else:
            labels = [("", "书目")]
        for identity, name in labels:
            groups.setdefault(identity, (name, []))[1].append(book)
    for identity, (name, members) in sorted(groups.items()):
        print(f"{name}" + (f" [{identity}]" if identity else ""))
        for book in members:
            print(f"  {book.id} | {book.title} | {book.edition} | {book.status}")


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "init-book":
            _initialize(args)
        elif args.command == "catalog":
            _catalog(args)
        elif args.command == "check-catalog":
            books = discover_books(args.root)
            print(f"书目元数据有效：{len(books)} 本；正文与 EPUB 检查尚未接入。")
        elif args.command == "plan":
            book_id = validate_id(args.id)
            book = load_book(args.root / "books" / book_id / "book.toml")
            print(f"{book.title} [{book.id}] 当前书目标记：{book.status}")
            print("以下阶段尚未实现 runner；书目标记不代表检查已通过。")
            for index, stage in enumerate(STAGES, 1):
                print(f"{index}. {stage.name}: {stage.purpose}\n   输出：{stage.output}\n   门禁：{stage.gate}")
    except (OSError, ValueError) as error:
        print(f"错误：{error}", file=sys.stderr)
        return 2
    return 0
