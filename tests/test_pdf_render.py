import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from hanqing.ingest import digest
from hanqing.pdf_render import render_pdf_page


class PdfRenderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.directory = self.root / 'data/work/sample'
        self.directory.mkdir(parents=True)
        self.source = self.directory / 'original.pdf'
        self.source.write_bytes(b'original source fixture')
        self.manifest = self.directory / 'manifest.json'
        self.manifest.write_text(json.dumps({
            'schema_version': 3, 'path_base': 'project', 'source_kind': 'pdf',
            'source_set_id': 'sample', 'source_id': 'sample-pdf', 'source_path': 'data/work/sample/original.pdf',
            'source_sha256': digest(self.source), 'files': [],
            'pdf_unpack': {'pages': [{'physical_page': 1, 'images': [], 'media_box': [0, 0, 100, 100],
                                      'crop_box': [0, 0, 100, 100], 'rotation': 0}]}
        }), encoding='utf-8')
        self.engine = MagicMock()
        self.engine.PYPDFIUM_INFO = 'fixture'
        self.engine.PDFIUM_INFO = 'fixture-pdfium'
        self.document = self.engine.PdfDocument.return_value.__enter__.return_value
        self.document.__len__.return_value = 1
        self.page = self.document.__getitem__.return_value
        self.page.get_size.return_value = (100, 100)
        image = self.page.render.return_value.to_pil.return_value.__enter__.return_value
        image.size = (100, 100)
        image.save.side_effect = lambda stream, **kwargs: stream.write(b'new PNG fixture')
        self.patch = patch('hanqing.pdf_render._pdfium', return_value=self.engine)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def render(self):
        return render_pdf_page(self.root, self.manifest, 1, dpi=72)

    def test_render_registered_separately_and_resume_preserves_bytes(self):
        record = self.render()
        output = self.root / record['path']
        before = (output.read_bytes(), output.stat().st_mtime_ns)
        self.assertEqual(self.render(), record)
        self.assertEqual(before, (output.read_bytes(), output.stat().st_mtime_ns))
        self.assertEqual(record['sha256'], digest(output))
        self.page.render.assert_called_once()
        self.page.close.assert_called_once()
        manifest = json.loads(self.manifest.read_text(encoding='utf-8'))
        self.assertEqual(manifest['pdf_unpack']['pages'][0]['images'], [])
        self.assertEqual(manifest['pdf_renderings'], [record])
        self.assertEqual(self.source.read_bytes(), b'original source fixture')

    def test_changed_source_and_unknown_page_rejected(self):
        with self.assertRaisesRegex(ValueError, 'absent from the unpacked'):
            render_pdf_page(self.root, self.manifest, 2)
        self.source.write_bytes(b'changed source')
        with self.assertRaisesRegex(ValueError, 'Original PDF path or bytes changed'):
            self.render()
        self.engine.PdfDocument.assert_not_called()

    def test_corrupt_render_is_preserved_and_rejected(self):
        record = self.render()
        output = self.root / record['path']
        output.write_bytes(b'altered render')
        with self.assertRaisesRegex(ValueError, 'configuration or bytes changed'):
            self.render()
        self.assertEqual(output.read_bytes(), b'altered render')

    def test_pixel_limit_rejects_before_render(self):
        self.page.get_size.return_value = (100000, 100000)
        with self.assertRaisesRegex(ValueError, 'pixel limit'):
            self.render()
        self.page.render.assert_not_called()
        self.page.close.assert_called_once()


if __name__ == '__main__':
    unittest.main()
