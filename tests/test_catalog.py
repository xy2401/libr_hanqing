"""Metadata validity does not depend on remote APIs or local source assets."""

from pathlib import Path
import tempfile
import unittest

from hanqing.catalog import discover_books, load_book
from hanqing.models import (
    BOOK_STATUSES, BookMetadata, CREATOR_ROLE_CODES, Creator, MetadataError, Series, validate_id,
)


_DRAFT = '''schema_version = 1
id = "example-book"
work_id = "example-work"
title = "古籍示例"
language = "zh-Hant"
edition = "0.1.0"
status = "draft"
'''


class CatalogTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def write_book(self, text: str = _DRAFT, folder: str = "example-book") -> Path:
        path = self.root / "books" / folder / "book.toml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def test_draft_can_be_anonymous(self) -> None:
        book = load_book(self.write_book())
        self.assertEqual(book.title, "古籍示例")
        self.assertEqual(book.creators, ())

    def test_multiple_creators_and_series(self) -> None:
        text = _DRAFT.replace('status = "draft"', 'status = "proofread"') + '''
[[creators]]
id = "author-a"
name = "甲"
[[creators]]
id = "editor-b"
name = "乙"
role = "editor"
[[series]]
id = "collection-a"
name = "甲丛书"
position = 2
[[series]]
id = "collection-b"
name = "乙丛书"
'''
        book = load_book(self.write_book(text))
        self.assertEqual([creator.role for creator in book.creators], ["author", "editor"])
        self.assertEqual([series.position for series in book.series], [2, None])

    def test_invalid_ids_and_windows_device_names(self) -> None:
        invalid = ("", "Book", "中文", "../book", "a_b", "-book", "book-", "a--b", "x" * 81,
                   "con", "prn", "aux", "nul", "com1", "lpt9")
        for identifier in invalid:
            with self.subTest(identifier=identifier), self.assertRaises(MetadataError):
                validate_id(identifier)
        self.assertEqual(validate_id("book-01"), "book-01")

    def test_book_id_must_match_directory(self) -> None:
        with self.assertRaisesRegex(MetadataError, "does not match directory"):
            load_book(self.write_book(folder="different-book"))

    def test_direct_construction_uses_the_same_content_validation(self) -> None:
        defaults = dict(
            schema_version=1, id="example-book", work_id="example-work",
            title="古籍示例", language="zh-Hant", edition="待补全", status="draft",
        )
        self.assertEqual(BookMetadata(**defaults).creators, ())
        for changes, message in (
            ({"id": "CON"}, "book.id"),
            ({"schema_version": True}, "schema_version"),
            ({"status": "done"}, "unsupported status"),
            ({"creators": (Creator("same", "甲"), Creator("same", "乙"))}, "duplicate ID"),
            ({"series": (Series("collection", "丛书", -1),)}, "positive integer"),
        ):
            with self.subTest(changes=changes), self.assertRaisesRegex(MetadataError, message):
                BookMetadata(**(defaults | changes))

    def test_illegal_xml_characters_are_rejected_before_writing_files(self) -> None:
        defaults = dict(
            schema_version=1, id="example-book", work_id="example-work",
            title="古籍示例", language="zh-Hant", edition="待补全", status="draft",
        )
        invalid = [chr(codepoint) for codepoint in range(0x20) if codepoint not in {9, 10, 13}]
        invalid += ["\ud800", "\udfff", "\ufffe", "\uffff"]
        for character in invalid:
            with self.subTest(codepoint=f"U+{ord(character):04X}"):
                with self.assertRaisesRegex(MetadataError, "book.title: invalid XML 1.0"):
                    BookMetadata(**(defaults | {"title": "题" + character + "名"}))
        changes = (
            {"edition": "初版\x01"},
            {"creators": (Creator("author", "作者\ud800"),)},
            {"series": (Series("collection", "丛书\uffff"),)},
        )
        for change in changes:
            with self.subTest(fields=list(change)), self.assertRaisesRegex(MetadataError, "invalid XML 1.0"):
                BookMetadata(**(defaults | change))
        self.assertFalse((self.root / "books").exists())

    def test_legal_xml_whitespace_and_supplementary_characters_are_accepted(self) -> None:
        title = "古籍\t题名\n分行\r说明𠮷"
        book = BookMetadata(
            schema_version=1, id="example-book", work_id="example-work",
            title=title, language="zh-Hant", edition="待补全", status="draft",
            creators=(Creator("author", "作者\n别号"),),
        )
        self.assertEqual(book.title, title)
        text = _DRAFT.replace('title = "古籍示例"', 'title = "古籍\\t题名\\n分行\\r说明𠮷"')
        self.assertEqual(load_book(self.write_book(text)).title, title)

    def test_creator_roles_are_supported_marc_roles(self) -> None:
        self.assertEqual(CREATOR_ROLE_CODES, {
            "author": "aut", "editor": "edt", "annotator": "ann",
            "translator": "trl", "compiler": "com", "commentator": "cwt",
        })
        for role in CREATOR_ROLE_CODES:
            text = _DRAFT + f'''[[creators]]
id = "creator"
name = "作者"
role = "{role}"
'''
            self.assertEqual(load_book(self.write_book(text)).creators[0].role, role)
        text = _DRAFT + '''[[creators]]
id = "creator"
name = "作者"
role = "publisher"
'''
        with self.assertRaisesRegex(MetadataError, "unsupported creator role"):
            load_book(self.write_book(text))

    def test_language_tags_check_syntax_without_claiming_registry_validity(self) -> None:
        for language in ("zh", "zh-Hant", "lzh-Hant", "en", "en-US", "zz"):
            with self.subTest(language=language):
                text = _DRAFT.replace('language = "zh-Hant"', f'language = "{language}"')
                self.assertEqual(load_book(self.write_book(text)).language, language)
        for language in ("zh Hant", " zh", "zh ", "zh_Hant", "zh--Hant", "zh-", "zh\\tHant", "zh\\nHant"):
            with self.subTest(language=language):
                text = _DRAFT.replace('language = "zh-Hant"', f'language = "{language}"')
                with self.assertRaisesRegex(MetadataError, "book.language"):
                    load_book(self.write_book(text))

    def test_scan_fields_are_rejected_for_every_catalog_status(self) -> None:
        source_table = '''
[[sources]]
id = "scan-001"
kind = "pdf"
path = "data/raw/source-set/original.pdf"
sha256 = "''' + "a" * 64 + '''"
'''
        for status in BOOK_STATUSES:
            base = _DRAFT.replace('status = "draft"', f'status = "{status}"')
            for suffix in (
                'primary_source_id = "scan-001"\n',
                'primary_source_id = ""\n',
                source_table,
                'primary_source_id = "scan-001"\n' + source_table,
            ):
                with self.subTest(status=status, suffix=suffix):
                    with self.assertRaisesRegex(MetadataError, r"belong in .*manifest\.json"):
                        load_book(self.write_book(base + suffix))

    def test_duplicate_ids_in_each_record_type(self) -> None:
        examples = {
            "creators": 'id = "same"\nname = "甲"\n',
            "series": 'id = "same"\nname = "甲丛书"\n',
        }
        for record_type, record in examples.items():
            with self.subTest(record_type=record_type):
                text = _DRAFT + f"\n[[{record_type}]]\n{record}\n[[{record_type}]]\n{record}"
                with self.assertRaisesRegex(MetadataError, "duplicate ID"):
                    load_book(self.write_book(text))

    def test_all_catalog_statuses_are_independent_of_local_scan_records(self) -> None:
        raw = self.root / "data" / "raw" / "source-set"
        raw.mkdir(parents=True)
        # 书目检查不读取本地来源清单；实际处理的来源验证由 ingest 负责。
        (raw / "manifest.json").write_text("invalid local manifest", encoding="utf-8")
        for status in BOOK_STATUSES:
            with self.subTest(status=status):
                text = _DRAFT.replace('status = "draft"', f'status = "{status}"')
                book = load_book(self.write_book(text))
                self.assertEqual(book.status, status)
                self.assertEqual(discover_books(self.root), [book])

    def test_schema_and_field_types_are_checked(self) -> None:
        changes = (
            ('schema_version = 1', 'schema_version = true', "schema_version"),
            ('schema_version = 1', 'schema_version = 2', "schema_version"),
            ('title = "古籍示例"', 'title = 42', "title: must be a string"),
            ('status = "draft"', 'status = "done"', "unsupported status"),
        )
        for old, new, message in changes:
            with self.subTest(new=new), self.assertRaisesRegex(MetadataError, message):
                load_book(self.write_book(_DRAFT.replace(old, new)))
        for suffix, message in (
            ("creators = 42\n", "creators: must be an array"),
            ("creators = [42]\n", "creators\\[0\\]: must be a table"),
            ("unexpected = true\n", "unknown field"),
            ('[[series]]\nid = "collection"\nname = "丛书"\nposition = true\n', "positive integer"),
        ):
            with self.subTest(suffix=suffix), self.assertRaisesRegex(MetadataError, message):
                load_book(self.write_book(_DRAFT + suffix))

    def test_discovery_is_sorted_and_does_not_require_asset_files(self) -> None:
        self.assertEqual(discover_books(self.root), [])
        self.write_book(_DRAFT.replace('id = "example-book"', 'id = "z-book"'), "z-book")
        self.write_book(_DRAFT.replace('id = "example-book"', 'id = "a-book"'), "a-book")
        self.assertEqual([book.id for book in discover_books(self.root)], ["a-book", "z-book"])

    def test_discovery_rejects_incomplete_visible_book_directories(self) -> None:
        self.write_book()
        incomplete = self.root / "books" / "incomplete"
        incomplete.mkdir()
        with self.assertRaisesRegex(MetadataError, "missing book.toml"):
            discover_books(self.root)

    def test_discovery_ignores_hidden_directories_and_placeholder_files(self) -> None:
        self.write_book()
        (self.root / "books" / ".gitkeep").touch()
        (self.root / "books" / ".cache").mkdir()
        self.assertEqual([book.id for book in discover_books(self.root)], ["example-book"])

    def test_invalid_toml_and_missing_file_report_metadata_error(self) -> None:
        with self.assertRaises(MetadataError):
            load_book(self.write_book("id = ["))
        with self.assertRaises(MetadataError):
            load_book(self.root / "books" / "missing" / "book.toml")


if __name__ == "__main__":
    unittest.main()
