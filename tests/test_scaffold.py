import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from hanqing.catalog import load_book
from hanqing.models import BookMetadata, Creator, Series
from hanqing.scaffold import initialize_book


class ScaffoldTests(unittest.TestCase):
    def test_unicode_xml_and_metadata_round_trip(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            book = BookMetadata(
                1, "test-edition", "test-work", '古籍 <輯> & "補"', "zh-Hant", "某刻本", "draft",
                creators=(Creator("author-one", "作者 & 氏"), Creator("commentator-one", "注疏者", "commentator")),
                series=(Series("classics", "經籍", 2),),
            )
            target = initialize_book(root, book)
            self.assertEqual(load_book(target / "book.toml"), book)
            metadata_text = (target / "book.toml").read_text(encoding="utf-8")
            for source_marker in ("sources", "primary_source_id", "data/raw/", "sha256", "scan-001"):
                self.assertNotIn(source_marker, metadata_text)
            self.assertEqual((target / "src/mimetype").read_bytes(), b"application/epub+zip")
            for pattern in ("*.xml", "*.xhtml", "*.opf"):
                for file in target.rglob(pattern):
                    ET.parse(file)
            package = ET.parse(target / "src/epub/content.opf")
            namespace = {"opf": "http://www.idpf.org/2007/opf"}
            roles = {
                entry.get("refines"): entry.text
                for entry in package.findall('.//opf:meta[@property="role"]', namespace)
            }
            self.assertEqual(roles, {"#creator-1": "aut", "#creator-2": "cwt"})
            self.assertFalse((root / "data").exists())

    def test_existing_edition_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            book = BookMetadata(1, "test-edition", "test-work", "古籍", "zh-Hant", "刻本", "draft")
            target = initialize_book(root, book)
            text = target / "src/epub/text/titlepage.xhtml"
            text.write_text("人工校勘成果", encoding="utf-8")
            with self.assertRaises(FileExistsError):
                initialize_book(root, book)
            self.assertEqual(text.read_text(encoding="utf-8"), "人工校勘成果")


if __name__ == "__main__":
    unittest.main()
