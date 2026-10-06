"""离线书目、出版提案与候选 EPUB CLI。"""

import argparse
import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from dataclasses import asdict
from pathlib import Path

from .catalog import discover_books, load_book
from .models import BookMetadata, Creator, Series, validate_id
from .pipeline import STAGES
from .scaffold import initialize_book
from .publication.assemble import assemble_book, accept_proposal
from .publication.xmlutil import project_path
from .workspace import migrate_data_layout
from .ingest import intake_pdfs
from .transcription import record_transcriptions
from .pdf_render import render_pdf_page
from .transcription_audit import audit_transcription_task
from .text_review import record_text_review
from .publication.package import build_candidate, run_epubcheck
from .publication.evidence import record_validation
from .validators.publication import check_source


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="hanqing", description="古籍数字化：书目、出版提案与候选 EPUB")
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
    plan = commands.add_parser("plan", help="显示处理阶段契约和实现范围，不执行处理")
    plan.add_argument("id", help="书籍 ID")
    assemble = commands.add_parser("assemble-book", help="按 work 清单的明确取舍生成 XHTML 提案，不覆盖出版正文")
    assemble.add_argument("id")
    assemble.add_argument("--manifest", required=True, type=Path)
    assemble.add_argument("--pandoc", default="pandoc", help="本地 Pandoc 程序路径")
    accept = commands.add_parser("accept-proposal", help="明确人工接受本轮转换提案；不提升校勘或发行状态")
    accept.add_argument("id")
    accept.add_argument("--manifest", required=True, type=Path)
    accept.add_argument("--reviewer", required=True)
    check = commands.add_parser("check-publication", help="检查一个 src/ 的资源、全书 ID、链接与目录")
    check.add_argument("source", type=Path)
    build = commands.add_parser("build-book", help="仅从 books/<id>/src/ 打候选包；不提升发行状态")
    build.add_argument("id")
    build.add_argument("--output", type=Path, help="本书 dist/ 中的新 EPUB 文件；默认 <id>.epub")
    build.add_argument("--epubcheck-jar", type=Path, help="本地官方 EPUBCheck jar；提供时检查候选包")
    build.add_argument("--java", default="java")
    migrate = commands.add_parser("migrate-data-layout", help="将旧 raw 工作区及书籍打包产物迁入新目录")
    migrate.add_argument("--check", action="store_true", help="只检查迁移范围，不写文件")
    intake = commands.add_parser("intake-pdfs", help="按显式清单接收 inbox PDF，无损提取内嵌图片流，不识别文字")
    intake.add_argument("--plan", required=True, type=Path)
    intake.add_argument("--check", action="store_true", help="核对输入与目标，不移动或解包")
    intake.add_argument("--resume", action="store_true", help="只恢复同一原件、同一哈希的未完成解包")
    transcription = commands.add_parser("record-transcriptions", help="登记助手看图写出的逐页稿和真实哈希，不执行识别")
    transcription.add_argument("--input", required=True, type=Path)
    transcription.add_argument("--revision-id", help="显式修订待校勘页稿，先保存原稿快照")
    transcription.add_argument("--revision-reason", help="本次看图更正或文字推校的依据")
    transcription.add_argument("--revision-method", choices=("assistant-direct-multimodal", "existing-markdown-context"), default="assistant-direct-multimodal")
    render = commands.add_parser("render-pdf-page", help="渲染明确的一页 PDF 供助手视读，登记来源与参数，不识别文字")
    render.add_argument("--manifest", required=True, type=Path)
    render.add_argument("--page", required=True, type=int, help="从 1 开始的物理页")
    render.add_argument("--dpi", type=int, default=300)
    audit = commands.add_parser("check-transcriptions", help="核验明确任务的页序与工作稿实际哈希，保存待校勘报告")
    audit.add_argument("--manifest", required=True, type=Path)
    audit.add_argument("--task", required=True)
    review = commands.add_parser("record-text-review", help="登记实际阅读的 Markdown 页稿及文字校勘判断，不自动判断正文")
    review.add_argument("--input", required=True, type=Path)
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
    print("状态：draft；请在 work 清单登记来源并添加校勘正文。")


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
            print(f"书目元数据有效：{len(books)} 本；此命令不验证正文或 EPUB。")
        elif args.command == "assemble-book":
            manifest = args.manifest if args.manifest.is_absolute() else args.root / args.manifest
            print(json.dumps(assemble_book(args.root, manifest, args.id, pandoc=args.pandoc), ensure_ascii=False, indent=2))
        elif args.command == "accept-proposal":
            manifest = args.manifest if args.manifest.is_absolute() else args.root / args.manifest
            print(json.dumps(accept_proposal(args.root, manifest, args.id, reviewer=args.reviewer), ensure_ascii=False, indent=2))
        elif args.command == "check-publication":
            source = args.source if args.source.is_absolute() else args.root / args.source
            print(json.dumps(check_source(source), ensure_ascii=False, indent=2))
        elif args.command == "build-book":
            root = args.root.resolve()
            book_id = validate_id(args.id)
            directory = project_path(root, f"books/{book_id}")
            book = load_book(directory / "book.toml")
            if book.id != book_id:
                raise ValueError("Book directory does not match its stable ID")
            distribution = project_path(root, f"books/{book_id}/dist")
            output = args.output or distribution / f"{book_id}.epub"
            relative = output.relative_to(root).as_posix() if output.is_absolute() else output.as_posix()
            output = project_path(root, relative)
            if output.parent != distribution or output.suffix != ".epub":
                raise ValueError("Build output must be an EPUB in this book's dist/")
            checker_path = output.with_suffix(".epubcheck.json")
            receipt = output.with_suffix(".build.json")
            for path in (output, checker_path, receipt, output.with_suffix(".validation.json")):
                if path.exists():
                    raise FileExistsError(f"Existing build bytes are preserved; choose a new --output: {path}")
            result = build_candidate(directory / "src", output)
            if args.epubcheck_jar:
                jar = args.epubcheck_jar if args.epubcheck_jar.is_absolute() else root / args.epubcheck_jar
                result["epubcheck"] = run_epubcheck(output, jar, checker_path, java=args.java)
                result["validation_summary"] = record_validation(root, directory, output, result)
                result["epubcheck"]["report"] = checker_path.relative_to(root).as_posix()
            else:
                result["epubcheck"] = {"status": "not-run"}
            result["candidate_path"] = output.relative_to(root).as_posix()
            result["book_id"] = book_id
            receipt.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
            result["build_record"] = receipt.relative_to(root).as_posix()
            print(json.dumps(result, ensure_ascii=False, indent=2))
            if result["epubcheck"]["status"] == "failed":
                return 2
        elif args.command == "migrate-data-layout":
            print(json.dumps(migrate_data_layout(args.root, check=args.check), ensure_ascii=False, indent=2))
        elif args.command == "intake-pdfs":
            plan = args.plan if args.plan.is_absolute() else args.root / args.plan
            def progress(item):
                print(f"{item['source_set_id']}: {item['completed_pages']}/{item['page_count']}", file=sys.stderr, flush=True)
            print(json.dumps(intake_pdfs(args.root, plan, check=args.check, resume=args.resume,
                                        progress=progress), ensure_ascii=False, indent=2))
        elif args.command == "record-transcriptions":
            source = args.input if args.input.is_absolute() else args.root / args.input
            print(json.dumps(record_transcriptions(args.root, source, revision_id=args.revision_id,
                                                   revision_reason=args.revision_reason, revision_method=args.revision_method), ensure_ascii=False, indent=2))
        elif args.command == "record-text-review":
            source = args.input if args.input.is_absolute() else args.root / args.input
            print(json.dumps(record_text_review(args.root, source), ensure_ascii=False, indent=2))
        elif args.command == "render-pdf-page":
            manifest = args.manifest if args.manifest.is_absolute() else args.root / args.manifest
            print(json.dumps(render_pdf_page(args.root, manifest, args.page, dpi=args.dpi), ensure_ascii=False, indent=2))
        elif args.command == "check-transcriptions":
            manifest = args.manifest if args.manifest.is_absolute() else args.root / args.manifest
            result = audit_transcription_task(args.root, manifest, args.task)
            print(json.dumps({key: result[key] for key in ('status', 'page_count', 'report_path', 'report_sha256')}, ensure_ascii=False, indent=2))
        elif args.command == "plan":
            book_id = validate_id(args.id)
            book = load_book(args.root / "books" / book_id / "book.toml")
            print(f"{book.title} [{book.id}] 当前书目标记：{book.status}")
            print("intake-pdfs、render-pdf-page、record-transcriptions、assemble-book、build-book 和出版结构/EPUBCheck 检查已接入；完整识别管理等阶段仍为契约。书目标记不代表检查已通过。")
            for index, stage in enumerate(STAGES, 1):
                print(f"{index}. {stage.name}: {stage.purpose}\n   输出：{stage.output}\n   门禁：{stage.gate}")
    except (OSError, ValueError, subprocess.SubprocessError, ET.ParseError) as error:
        print(f"错误：{error}", file=sys.stderr)
        return 2
    return 0
