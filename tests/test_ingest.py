"""Encoded byte preservation and interruption checks; no OCR or rendering."""

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zlib

from hanqing.ingest import digest, inspect_pdf, intake_pdf, intake_pdfs


@unittest.skipUnless(importlib.util.find_spec('pypdf'), 'optional PDF runtime is not installed')
class PdfIntakeTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        (self.root / 'data/inbox').mkdir(parents=True)

    def fixture(self, name='example.pdf', filters='/DCTDecode', pages=2, multiple=False, text_page=False):
        from pypdf import PdfWriter
        from pypdf.generic import DictionaryObject, NameObject, NumberObject, EncodedStreamObject, DecodedStreamObject
        writer = PdfWriter()
        payloads = []
        for number in range(pages):
            page = writer.add_blank_page(width=100, height=200)
            objects = DictionaryObject()
            operations = []
            for image_number in range(0 if text_page else (2 if multiple else 1)):
                # Deliberate encoded byte sentinels, not an image decoding test.
                raw = b'\xff\xd8' + f'encoded-{number}-{image_number}'.encode() + b'\xff\xd9'
                if filters == '/FlateDecode':
                    raw = zlib.compress(bytes([number, image_number, 200]))
                payloads.append(raw)
                image = EncodedStreamObject()
                image._data = raw
                image.update({NameObject('/Type'): NameObject('/XObject'), NameObject('/Subtype'): NameObject('/Image'),
                              NameObject('/Filter'): NameObject(filters), NameObject('/Width'): NumberObject(1),
                              NameObject('/Height'): NumberObject(1), NameObject('/BitsPerComponent'): NumberObject(8),
                              NameObject('/ColorSpace'): NameObject('/DeviceRGB')})
                resource = f'/image-{image_number}'
                objects[NameObject(resource)] = writer._add_object(image)
                operations.append(f'q 100 0 0 200 0 0 cm {resource} Do Q\n'.encode())
            page[NameObject('/Resources')] = DictionaryObject({NameObject('/XObject'): objects})
            if text_page:
                raw = b'BT /F0 10 Tf 10 10 Td (original native text) Tj ET\n'
                operations = [raw]
                payloads.append(raw)
                font = DictionaryObject({NameObject('/Type'):NameObject('/Font'), NameObject('/Subtype'):NameObject('/Type1'),
                                         NameObject('/BaseFont'):NameObject('/Helvetica')})
                page[NameObject('/Resources')][NameObject('/Font')] = DictionaryObject({NameObject('/F0'):writer._add_object(font)})
            content = DecodedStreamObject()
            content.set_data(b''.join(operations))
            page[NameObject('/Contents')] = writer._add_object(content)
        writer.add_metadata({'/Title': '原始掃描', '/Author': '來源編者'})
        path = self.root / 'data/inbox' / name
        writer.write(path)
        writer.close()
        return path, payloads

    def row(self, path, identity='example-source'):
        return {'source_set_id': identity, 'source_path': path.relative_to(self.root).as_posix(),
                'source_sha256': digest(path)}

    def manifest(self, identity='example-source'):
        return self.root / 'data/work' / identity / 'manifest.json'

    def test_jpeg_streams_and_original_are_byte_exact_without_books(self):
        path, payloads = self.fixture()
        before = path.read_bytes()
        result = intake_pdf(self.root, self.row(path))
        data = json.loads(self.manifest().read_text(encoding='utf-8'))
        self.assertEqual(result['pages'], 2)
        self.assertEqual(result['single_full_page_image_pages'], 2)
        self.assertFalse(path.exists())
        self.assertEqual((self.manifest().parent/'original.pdf').read_bytes(), before)
        self.assertEqual(data['books'], [])
        self.assertFalse((self.root/'books').exists())
        for number, payload in enumerate(payloads, 1):
            target = self.manifest().parent/'unpacked'/f'page-{number:04d}.jpg'
            self.assertEqual(target.read_bytes(), payload)
            self.assertEqual(data['pdf_unpack']['pages'][number-1]['images'][0]['sha256'], digest(target))
        self.assertEqual(data['pdf_metadata']['/Author'], '來源編者')

    def test_non_jpeg_encoded_stream_is_not_decoded_or_reencoded(self):
        path, payloads = self.fixture(filters='/FlateDecode', pages=1)
        intake_pdf(self.root, self.row(path))
        self.assertEqual((self.manifest().parent/'unpacked/page-0001.bin').read_bytes(), payloads[0])
        data = json.loads(self.manifest().read_text(encoding='utf-8'))
        self.assertEqual(data['pdf_unpack']['pages'][0]['images'][0]['dictionary']['/Filter'], '/FlateDecode')

    def test_multiple_images_keep_explicit_physical_page_mapping(self):
        path, payloads = self.fixture(pages=1, multiple=True)
        result = intake_pdf(self.root, self.row(path))
        self.assertEqual(result['images'], 2)
        self.assertEqual(result['single_full_page_image_pages'], 0)
        data = json.loads(self.manifest().read_text(encoding='utf-8'))
        images = data['pdf_unpack']['pages'][0]['images']
        for number, image in enumerate(images, 1):
            self.assertEqual((self.root/image['path']).read_bytes(), payloads[number-1])
            self.assertTrue(image['path'].endswith(f'page-0001-image-{number:02d}.jpg'))

    def test_native_text_page_keeps_encoded_content_and_font_references(self):
        path, payloads = self.fixture(pages=1, text_page=True)
        result = intake_pdf(self.root, self.row(path))
        self.assertEqual(result['pages'], 1)
        self.assertEqual(result['images'], 0)
        target = self.manifest().parent/'unpacked/page-0001-content-01.bin'
        self.assertEqual(target.read_bytes(), payloads[0])
        page = json.loads(self.manifest().read_text(encoding='utf-8'))['pdf_unpack']['pages'][0]
        self.assertEqual(page['content_streams'][0]['sha256'], digest(target))
        self.assertIn('/Font', page['resources'])

    def test_blank_page_is_explicitly_recorded_without_inventing_an_image(self):
        from pypdf import PdfWriter
        writer = PdfWriter()
        writer.add_blank_page(width=100, height=200)
        path = self.root/'data/inbox/blank.pdf'
        writer.write(path)
        writer.close()
        result = intake_pdf(self.root, self.row(path))
        self.assertEqual(result['pages'], 1)
        self.assertEqual(result['images'], 0)
        page = json.loads(self.manifest().read_text(encoding='utf-8'))['pdf_unpack']['pages'][0]
        self.assertEqual(page['content_streams'], [])
        self.assertEqual(page['graphics_operators'], [])

    def test_batch_hash_conflict_refuses_before_moving_any_original(self):
        first, _ = self.fixture('first.pdf', pages=1)
        second, _ = self.fixture('second.pdf', pages=1)
        rows = [self.row(first, 'first-source'), self.row(second, 'second-source')]
        rows[1]['source_sha256'] = '0'*64
        plan = self.root/'plan.json'
        plan.write_text(json.dumps({'schema_version': 1, 'files': rows}), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'SHA-256 changed'):
            intake_pdfs(self.root, plan)
        self.assertTrue(first.is_file())
        self.assertTrue(second.is_file())
        self.assertFalse((self.root/'data/work').exists())

    def test_preflight_writes_nothing_and_existing_work_is_preserved(self):
        path, _ = self.fixture(pages=1)
        inspected = inspect_pdf(self.root, path.relative_to(self.root).as_posix(), 'example-source')
        self.assertEqual(inspected['page_count'], 1)
        self.assertFalse((self.root/'data/work').exists())
        row = self.row(path)
        intake_pdf(self.root, row)
        with self.assertRaises(FileExistsError):
            intake_pdf(self.root, row)

    def test_interruption_resumes_missing_pages_without_overwriting_saved_bytes(self):
        path, payloads = self.fixture()
        row = self.row(path)
        original_open = Path.open

        def open_file(target, *args, **kwargs):
            if target.name == 'page-0002.jpg' and args and args[0] == 'xb':
                raise OSError('simulated interrupted output')
            return original_open(target, *args, **kwargs)

        with patch.object(Path, 'open', open_file):
            with self.assertRaises(OSError):
                intake_pdf(self.root, row)
        first = self.manifest().parent/'unpacked/page-0001.jpg'
        modified = first.stat().st_mtime_ns
        state = json.loads(self.manifest().read_text(encoding='utf-8'))['pdf_unpack']
        self.assertEqual(state['status'], 'interrupted')
        self.assertEqual(state['completed_pages'], 1)
        result = intake_pdf(self.root, row, resume=True)
        self.assertEqual(result['pages'], 2)
        self.assertEqual(first.stat().st_mtime_ns, modified)
        self.assertEqual((first.parent/'page-0002.jpg').read_bytes(), payloads[1])

    def test_completed_image_corruption_is_rejected_and_preserved(self):
        path, _ = self.fixture(pages=1)
        row = self.row(path)
        intake_pdf(self.root, row)
        target = self.manifest().parent/'unpacked/page-0001.jpg'
        target.write_bytes(b'changed output')
        with self.assertRaisesRegex(ValueError, 'Existing image bytes differ'):
            intake_pdf(self.root, row, resume=True)
        self.assertEqual(target.read_bytes(), b'changed output')

    def test_path_traversal_input_is_rejected(self):
        with self.assertRaises(ValueError):
            inspect_pdf(self.root, 'data/inbox/../../outside.pdf', 'example-source')


if __name__ == '__main__':
    unittest.main()
