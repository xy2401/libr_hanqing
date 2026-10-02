"""Metadata validity does not depend on remote APIs or local source assets."""

from pathlib import Path
import tempfile
import unittest

from hanqing.catalog import discover_books, load_book
from hanqing.models import (
    BookMetadata, CREATOR_ROLE_CODES, Creator, MetadataError, Series, Source, validate_id,
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

    def test_draft_can_be_anonymous_without_sources(self) -> None:
        book = load_book(self.write_book())
        self.assertEqual(book.title, "古籍示例")
        self.assertEqual(book.creators, ())
        self.assertEqual(book.sources, ())
        self.assertEqual(book.primary_source_id, "")

    def test_multiple_creators_series_and_sources(self) -> None:
        text = _DRAFT.replace('status = "draft"', 'status = "proofread"') + '''
primary_source_id = "edition-a"
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
[[sources]]
id = "edition-a"
kind = "pdf"
path = "data/raw/example-book/edition-a/scan.pdf"
sha256 = "''' + "A" * 64 + '''"
[[sources]]
id = "edition-b"
kind = "epub"
path = "data/raw/example-book/edition-b/original.epub"
sha256 = "''' + "b" * 64 + '''"
'''
        book = load_book(self.write_book(text))
        self.assertEqual([creator.role for creator in book.creators], ["author", "editor"])
        self.assertEqual([series.position for series in book.series], [2, None])
        self.assertEqual(book.sources[0].sha256, "a" * 64)
        self.assertEqual(len(book.sources), 2)

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
        self.assertEqual(BookMetadata(**defaults).sources, ())
        for changes, message in (
            ({"id": "CON"}, "book.id"),
            ({"schema_version": True}, "schema_version"),
            ({"status": "ready"}, "at least one source"),
            ({"creators": (Creator("same", "甲"), Creator("same", "乙"))}, "duplicate ID"),
            ({"primary_source_id": "edition-a", "sources": (
                Source("edition-a", "pdf", "../scan.pdf"),
            )}, "sources\\[0\\].path"),
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
            {"primary_source_id": "scan", "sources": (
                Source("scan", "pdf", "data/raw/example-book/scan/a.pdf", description="底本\x02"),
            )},
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

    def test_relative_source_paths_are_scoped_and_cannot_traverse(self) -> None:
        invalid = (
            "../scan.pdf", "/data/raw/example-book/edition-a/scan.pdf",
            "C:/data/raw/example-book/edition-a/scan.pdf",
            "C:data/raw/example-book/edition-a/scan.pdf",
            "data/raw/example-book/edition-a/../scan.pdf",
            "data/raw/other-book/edition-a/scan.pdf",
            "data/raw/example-book/other-source/scan.pdf",
            "data/raw/example-book/edition-a/./scan.pdf",
            "data/raw/example-book/edition-a//scan.pdf",
            "data/raw/example-book/edition-a/scan.pdf:stream",
            "data\\raw\\example-book\\edition-a\\scan.pdf",
        )
        for source_path in invalid:
            with self.subTest(path=source_path):
                escaped = source_path.replace("\\", "\\\\")
                text = _DRAFT + f'''
primary_source_id = "edition-a"
[[sources]]
id = "edition-a"
kind = "pdf"
path = "{escaped}"
'''
                with self.assertRaisesRegex(MetadataError, "sources\\[0\\].path"):
                    load_book(self.write_book(text))

    def test_duplicate_ids_in_each_record_type(self) -> None:
        examples = {
            "creators": 'id = "same"\nname = "甲"\n',
            "series": 'id = "same"\nname = "甲丛书"\n',
            "sources": 'id = "same"\nkind = "pdf"\npath = "data/raw/example-book/same/a.pdf"\n',
        }
        for record_type, record in examples.items():
            with self.subTest(record_type=record_type):
                text = _DRAFT + f"\n[[{record_type}]]\n{record}\n[[{record_type}]]\n{record}"
                with self.assertRaisesRegex(MetadataError, "duplicate ID"):
                    load_book(self.write_book(text))

    def test_non_draft_requires_sources_and_hashes(self) -> None:
        for status in ("recognized", "proofread", "ready", "released"):
            with self.subTest(status=status):
                text = _DRAFT.replace('status = "draft"', f'status = "{status}"')
                with self.assertRaisesRegex(MetadataError, "at least one source"):
                    load_book(self.write_book(text))
                text += '''
primary_source_id = "edition-a"
[[sources]]
id = "edition-a"
kind = "pdf"
path = "data/raw/example-book/edition-a/scan.pdf"
'''
                with self.assertRaisesRegex(MetadataError, "sha256: required"):
                    load_book(self.write_book(text))

    def test_primary_source_must_identify_a_source(self) -> None:
        text = _DRAFT + '''
primary_source_id = "missing"
[[sources]]
id = "edition-a"
kind = "pdf"
path = "data/raw/example-book/edition-a/scan.pdf"
'''
        with self.assertRaisesRegex(MetadataError, "existing source"):
            load_book(self.write_book(text))
        with self.assertRaisesRegex(MetadataError, "without a source"):
            load_book(self.write_book(_DRAFT + 'primary_source_id = "missing"\n'))

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

    def test_hash_and_source_kind_are_checked(self) -> None:
        prefix = _DRAFT + '''
primary_source_id = "edition-a"
[[sources]]
id = "edition-a"
kind = "pdf"
path = "data/raw/example-book/edition-a/scan.pdf"
'''
        with self.assertRaisesRegex(MetadataError, "64 hexadecimal"):
            load_book(self.write_book(prefix + 'sha256 = "abc"\n'))
        with self.assertRaisesRegex(MetadataError, "must be 'pdf' or 'epub'"):
            load_book(self.write_book(prefix.replace('kind = "pdf"', 'kind = "image"')))

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
