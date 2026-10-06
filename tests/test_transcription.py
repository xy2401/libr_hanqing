import copy
import json
from pathlib import Path
import tempfile
import unittest

from hanqing.ingest import digest
from hanqing.transcription import record_transcriptions
from hanqing.transcription_audit import audit_transcription_task
from hanqing.text_review import record_text_review


class TranscriptionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.directory = self.root / 'data/work/sample'
        (self.directory / 'unpacked').mkdir(parents=True)
        self.source = self.directory / 'original.pdf'
        self.source.write_bytes(b'preserved source fixture')
        self.image = self.directory / 'unpacked/page-0001.jpg'
        self.image.write_bytes(b'image hash fixture; not decoded')
        for relative in ('src/hanqing/prompts/transcribe-page-v1.txt', 'schemas/page-transcription.schema.json'):
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes((Path(__file__).resolve().parents[1] / relative).read_bytes())
        self.manifest = self.directory / 'manifest.json'
        self.manifest.write_text(json.dumps({
            'schema_version': 3, 'path_base': 'project', 'source_set_id': 'sample', 'source_id': 'sample-pdf',
            'source_path': 'data/work/sample/original.pdf', 'source_sha256': digest(self.source), 'books': [], 'files': [],
            'pdf_unpack': {'pages': [{'physical_page': 1, 'images': [{'path': 'data/work/sample/unpacked/page-0001.jpg', 'sha256': digest(self.image)}]}]},
        }), encoding='utf-8')
        self.data = {'schema_version': 1, 'method': 'assistant-direct-multimodal', 'source_set_id': 'sample',
                     'source_sha256': digest(self.source), 'run_id': 'trial', 'markdown_directory': 'data/work/sample/md.example',
                     'scope': {'first_physical_page': 1, 'last_physical_page': 1}, 'assistant': 'test', 'model': None,
                     'pages': [{'image_path': 'data/work/sample/unpacked/page-0001.jpg', 'image_sha256': digest(self.image),
                                'transcription': {'source_id': 'sample-pdf', 'physical_page': 1, 'printed_page_label': '甲',
                                                  'warnings': ['待核'], 'blocks': [{'id': 'a', 'kind': 'main', 'reading_order': 1,
                                                                                 'text': '異體爲①\n原句。', 'bbox': [0, 0, 1, 1], 'uncertainties': ['字形待核']}]}}]}
        self.input = self.root / 'data/input.json'

    def record(self, data=None):
        self.input.write_text(json.dumps(data or self.data, ensure_ascii=False), encoding='utf-8')
        return record_transcriptions(self.root, self.input)

    def test_exact_text_coordinates_and_unproofread_state(self):
        result = self.record()
        self.assertEqual(result['status'], 'scoped-transcription-draft-complete')
        content = (self.directory / 'md.example/page-0001.md').read_text(encoding='utf-8')
        self.assertIn('異體爲①\n原句。', content)
        manifest = json.loads(self.manifest.read_text(encoding='utf-8'))
        self.assertEqual(manifest['books'], [])
        self.assertEqual(manifest['recognition_runs'][0]['pages'][0]['transcription'], self.data['pages'][0]['transcription'])
        self.assertTrue(manifest['manifest_history'])

    def test_resume_preserves_bytes_and_modified_time(self):
        self.record()
        path = self.directory / 'md.example/page-0001.md'
        before = (path.read_bytes(), path.stat().st_mtime_ns)
        self.record()
        self.assertEqual(before, (path.read_bytes(), path.stat().st_mtime_ns))
        self.assertEqual(len(json.loads(self.manifest.read_text(encoding='utf-8'))['recognition_runs'][0]['pages']), 1)

    def test_changed_image_rejected_before_markdown_write(self):
        self.image.write_bytes(b'changed image')
        with self.assertRaisesRegex(ValueError, 'image hash differs'):
            self.record()
        self.assertFalse((self.directory / 'md.example').exists())

    def test_previous_text_and_corrupt_markdown_rejected(self):
        self.record()
        changed = copy.deepcopy(self.data)
        changed['pages'][0]['transcription']['blocks'][0]['text'] = '擅改'
        with self.assertRaisesRegex(ValueError, 'Completed transcription differs'):
            self.record(changed)
        path = self.directory / 'md.example/page-0001.md'
        path.write_text('外部修改', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'refusing to overwrite'):
            self.record()
        self.assertEqual(path.read_text(encoding='utf-8'), '外部修改')

    def test_invalid_order_and_traversal_rejected(self):
        changed = copy.deepcopy(self.data)
        changed['pages'][0]['transcription']['blocks'][0]['reading_order'] = 2
        with self.assertRaisesRegex(ValueError, 'reading order'):
            self.record(changed)
        changed = copy.deepcopy(self.data)
        changed['markdown_directory'] = 'data/work/sample/../md.example'
        with self.assertRaisesRegex(ValueError, 'Invalid project-relative path'):
            self.record(changed)

    def test_scope_rejects_page_before_writing(self):
        changed = copy.deepcopy(self.data)
        changed['scope'] = {'first_physical_page': 2, 'last_physical_page': 2}
        with self.assertRaisesRegex(ValueError, 'outside the declared scope'):
            self.record(changed)
        self.assertFalse((self.directory / 'md.example').exists())

    def test_explicit_revision_preserves_snapshot_and_original_record(self):
        self.record()
        path = self.directory / 'md.example/page-0001.md'
        original = path.read_bytes()
        changed = copy.deepcopy(self.data)
        changed['pages'][0]['transcription']['blocks'][0]['text'] = '圖證更正①'
        self.input.write_text(json.dumps(changed, ensure_ascii=False), encoding='utf-8')
        record_transcriptions(self.root, self.input, revision_id='glyph-fix', revision_reason='放大原頁確認')
        self.assertEqual(path.with_name('page-0001.glyph-fix.original.md').read_bytes(), original)
        manifest = json.loads(self.manifest.read_text(encoding='utf-8'))
        page = manifest['recognition_runs'][0]['pages'][0]
        self.assertEqual(page['markdown_sha256'], digest(path))
        self.assertEqual(page['revisions'][0]['previous_record']['transcription'], self.data['pages'][0]['transcription'])
        self.assertEqual(manifest['books'], [])
        self.assertEqual(manifest['recognition_runs'][0]['status'], 'scoped-transcription-draft-complete')

    def test_expanded_run_reuses_page_without_duplicate_inventory(self):
        self.record()
        path = self.directory / 'md.example/page-0001.md'
        before = (path.read_bytes(), path.stat().st_mtime_ns)
        changed = copy.deepcopy(self.data)
        changed['run_id'] = 'full-scope'
        changed['scope']['last_physical_page'] = 2
        self.record(changed)
        manifest = json.loads(self.manifest.read_text(encoding='utf-8'))
        self.assertEqual(sum(f['path'].endswith('/page-0001.md') for f in manifest['files']), 1)
        self.assertEqual(before, (path.read_bytes(), path.stat().st_mtime_ns))
        self.assertEqual(manifest['recognition_runs'][1]['pages'][0]['reused_from_run_id'], 'trial')

    def rendered_fixture(self):
        manifest = json.loads(self.manifest.read_text(encoding='utf-8'))
        manifest['pdf_unpack']['pages'][0]['images'] = []
        manifest['pdf_renderings'] = [{'schema_version': 1, 'kind': 'pdf-full-page-render',
                                      'physical_page': 1, 'path': self.data['pages'][0]['image_path'],
                                      'sha256': digest(self.image), 'source_path': manifest['source_path'],
                                      'source_sha256': manifest['source_sha256'],
                                      'parameters': {'additional_crop_lbrt': [0, 0, 0, 0], 'additional_rotation': 0}}]
        self.manifest.write_text(json.dumps(manifest), encoding='utf-8')
        return manifest

    def test_registered_full_page_render_is_recorded_with_provenance(self):
        manifest = self.rendered_fixture()
        self.record()
        saved = json.loads(self.manifest.read_text(encoding='utf-8'))['recognition_runs'][0]['pages'][0]
        self.assertEqual(saved['image_origin'], manifest['pdf_renderings'][0])

    def test_render_wrong_source_or_crop_is_rejected_before_writing(self):
        original = self.rendered_fixture()
        for changed in ('source_sha256', 'parameters'):
            manifest = copy.deepcopy(original)
            if changed == 'parameters':
                manifest['pdf_renderings'][0]['parameters']['additional_crop_lbrt'][0] = 1
            else:
                manifest['pdf_renderings'][0]['source_sha256'] = 'bad'
            self.manifest.write_text(json.dumps(manifest), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'full-page parameters differ'):
                self.record()
            self.assertFalse((self.directory / 'md.example').exists())

    def audit_fixture(self):
        self.record()
        manifest = json.loads(self.manifest.read_text(encoding='utf-8'))
        manifest['recognition_tasks'] = [{'task_id': 'whole-example', 'method': 'assistant-direct-multimodal',
                                         'scope': {'first_physical_page': 1, 'last_physical_page': 1},
                                         'regions': [{'label': '正文', 'first': 1, 'last': 1, 'run_id': 'trial'}]}]
        self.manifest.write_text(json.dumps(manifest), encoding='utf-8')
        return manifest

    def test_task_audit_saves_coverage_and_keeps_proofreading_pending(self):
        self.audit_fixture()
        result = audit_transcription_task(self.root, self.manifest, 'whole-example')
        self.assertEqual(result['completed_pages'], [1])
        self.assertEqual(result['proofreading'], 'not-performed')
        self.assertEqual(result['report_sha256'], digest(self.root / result['report_path']))
        self.assertEqual(json.loads(self.manifest.read_text(encoding='utf-8'))['books'], [])

    def test_task_audit_rejects_page_gap_and_changed_markdown(self):
        manifest = self.audit_fixture()
        manifest['recognition_tasks'][0]['scope']['last_physical_page'] = 2
        self.manifest.write_text(json.dumps(manifest), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'gap at the task end'):
            audit_transcription_task(self.root, self.manifest, 'whole-example')
        manifest['recognition_tasks'][0]['scope']['last_physical_page'] = 1
        self.manifest.write_text(json.dumps(manifest), encoding='utf-8')
        (self.directory / 'md.example/page-0001.md').write_text('改稿', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'Actual file hash differs'):
            audit_transcription_task(self.root, self.manifest, 'whole-example')
        self.assertFalse((self.directory / 'editorial.whole-example').exists())

    def test_text_revision_requires_actual_quote_and_records_method(self):
        self.record()
        changed = copy.deepcopy(self.data)
        changed['pages'][0]['transcription']['blocks'][0]['text'] = '異體爲①\n文内修訂。'
        path = self.directory / 'md.example/page-0001.md'
        reference = {'path': path.relative_to(self.root).as_posix(), 'sha256': digest(path), 'quote': '不存在'}
        changed['pages'][0]['text_evidence'] = [reference]
        self.input.write_text(json.dumps(changed, ensure_ascii=False), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'evidence path, hash or quote differs'):
            record_transcriptions(self.root, self.input, revision_id='text-one', revision_reason='文内依据', revision_method='existing-markdown-context')
        self.assertFalse(path.with_name('page-0001.text-one.original.md').exists())
        reference['quote'] = '異體爲①\n原句。'
        self.input.write_text(json.dumps(changed, ensure_ascii=False), encoding='utf-8')
        record_transcriptions(self.root, self.input, revision_id='text-one', revision_reason='文内依据', revision_method='existing-markdown-context')
        revision = json.loads(self.manifest.read_text(encoding='utf-8'))['recognition_runs'][0]['pages'][0]['revisions'][0]
        self.assertEqual(revision['method'], 'existing-markdown-context')
        self.assertEqual(revision['text_evidence'][0]['input_snapshot'], revision['previous_snapshot'])

    def text_review_fixture(self):
        self.audit_fixture()
        path = self.directory / 'editorial.text-pass/input.json'
        path.parent.mkdir()
        value = {'schema_version': 1, 'source_set_id': 'sample', 'review_id': 'text-pass', 'task_id': 'whole-example',
                 'method': 'existing-markdown-context', 'policy': '只据明确文内证据修订，未定读保留',
                 'pages': [{'physical_page': 1, 'markdown_path': 'data/work/sample/md.example/page-0001.md',
                            'markdown_sha256': digest(self.directory / 'md.example/page-0001.md'),
                            'notes': ['已读，保留字形'], 'findings': []}]}
        path.write_text(json.dumps(value), encoding='utf-8')
        return path, value

    def test_text_review_checkpoint_requires_current_input_and_does_not_accept_book(self):
        path, value = self.text_review_fixture()
        result = record_text_review(self.root, path)
        self.assertEqual(result['status'], 'text-reading-pass-complete-pending-image-check')
        manifest = json.loads(self.manifest.read_text(encoding='utf-8'))
        self.assertEqual(manifest['books'], [])
        self.assertEqual(manifest['text_reviews'][0]['image_collation'], 'not-performed')
        value['pages'][0]['markdown_sha256'] = 'stale'
        path.write_text(json.dumps(value), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'Markdown bytes differ'):
            record_text_review(self.root, path)

    def test_text_review_rejects_invented_quote_and_duplicate_page(self):
        path, value = self.text_review_fixture()
        value['pages'][0]['findings'] = [{'id': 'doubt', 'quote': '稿件未有', 'reason': '待核', 'status': 'pending-image-check'}]
        path.write_text(json.dumps(value), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'current text quote'):
            record_text_review(self.root, path)
        value['pages'][0]['findings'] = []
        value['pages'].append(copy.deepcopy(value['pages'][0]))
        path.write_text(json.dumps(value), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'Duplicate or out-of-task'):
            record_text_review(self.root, path)

    def test_shared_pilot_still_points_to_old_bytes_after_revision(self):
        self.record()
        expanded = copy.deepcopy(self.data)
        expanded['run_id'] = 'expanded'
        self.record(expanded)
        changed = copy.deepcopy(expanded)
        path = self.directory / 'md.example/page-0001.md'
        before = path.read_bytes()
        changed['pages'][0]['transcription']['blocks'][0]['text'] = '文内推校'
        changed['pages'][0]['text_evidence'] = [{'path': path.relative_to(self.root).as_posix(),
                                               'sha256': digest(path), 'quote': '原句。'}]
        self.input.write_text(json.dumps(changed), encoding='utf-8')
        record_transcriptions(self.root, self.input, revision_id='text-fix', revision_reason='文内依据',
                              revision_method='existing-markdown-context')
        manifest = json.loads(self.manifest.read_text(encoding='utf-8'))
        pilot, current = manifest['recognition_runs']
        old_page = pilot['pages'][0]
        self.assertEqual((self.root / old_page['markdown_path']).read_bytes(), before)
        self.assertEqual(digest(self.root / old_page['markdown_path']), old_page['markdown_sha256'])
        self.assertEqual(digest(self.root / pilot['page_map']), pilot['page_map_sha256'])
        self.assertEqual(current['pages'][0]['markdown_path'], path.relative_to(self.root).as_posix())

    def test_later_text_explanation_keeps_original_finding_and_requires_real_evidence(self):
        path, value = self.text_review_fixture()
        finding = {'id': 'old-name', 'quote': '異體', 'reason': '疑为别读', 'status': 'pending-image-check'}
        value['pages'][0]['findings'] = [finding]
        path.write_text(json.dumps(value), encoding='utf-8')
        record_text_review(self.root, path)
        resolution = {'finding_id': 'old-name', 'status': 'retained-from-text', 'reason': '后文说明为原用名',
                      'evidence': [{**{k: value['pages'][0][k] for k in ('physical_page', 'markdown_path', 'markdown_sha256')},
                                    'quote': '未有此句'}]}
        value['resolutions'] = [resolution]
        path.write_text(json.dumps(value), encoding='utf-8')
        before = self.manifest.read_bytes()
        with self.assertRaisesRegex(ValueError, 'quote current task Markdown'):
            record_text_review(self.root, path)
        self.assertEqual(self.manifest.read_bytes(), before)
        resolution['evidence'][0]['quote'] = '原句。'
        path.write_text(json.dumps(value), encoding='utf-8')
        record_text_review(self.root, path)
        review = json.loads(self.manifest.read_text(encoding='utf-8'))['text_reviews'][0]
        self.assertEqual(review['pages'][0]['findings'], [finding])
        self.assertEqual(review['finding_counts']['pending-image-check'], 0)
        self.assertEqual(review['finding_counts']['retained-from-text'], 1)
        self.assertEqual(review['image_collation'], 'not-performed')

    def test_changed_previously_read_page_invalidates_whole_current_pass(self):
        path, value = self.text_review_fixture()
        record_text_review(self.root, path)
        manifest = json.loads(self.manifest.read_text(encoding='utf-8'))
        manifest['pdf_unpack']['pages'].append({'physical_page': 2, 'images': manifest['pdf_unpack']['pages'][0]['images']})
        task = manifest['recognition_tasks'][0]
        task['scope']['last_physical_page'] = 2
        task['regions'] = [{'label': '全文', 'first': 1, 'last': 2, 'run_id': 'expanded'}]
        self.manifest.write_text(json.dumps(manifest), encoding='utf-8')
        expanded = copy.deepcopy(self.data)
        expanded['run_id'] = 'expanded'
        expanded['scope']['last_physical_page'] = 2
        second = copy.deepcopy(expanded['pages'][0])
        second['transcription']['physical_page'] = 2
        expanded['pages'].append(second)
        self.record(expanded)
        first_path = self.directory / 'md.example/page-0001.md'
        first_path.write_text('外部改稿', encoding='utf-8')
        second_path = self.directory / 'md.example/page-0002.md'
        value['pages'][0].update(physical_page=2, markdown_path=second_path.relative_to(self.root).as_posix(),
                                 markdown_sha256=digest(second_path))
        path.write_text(json.dumps(value), encoding='utf-8')
        result = record_text_review(self.root, path)
        self.assertEqual(result['stale_pages'], [1])
        self.assertEqual(result['status'], 'partial-text-review')


if __name__ == '__main__':
    unittest.main()
