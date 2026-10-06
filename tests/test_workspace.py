from contextlib import redirect_stdout, redirect_stderr
import io
import json
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET
from unittest.mock import patch

from hanqing.cli import main
from hanqing.models import BookMetadata, Creator
from hanqing.publication.assemble import digest
from hanqing.publication.evidence import record_validation
from hanqing.publication.xmlutil import NS, OPF, write_xml
from hanqing.scaffold import initialize_book
from hanqing.workspace import migrate_data_layout


class WorkspaceMigrationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / 'data/raw/source-set'
        self.source.mkdir(parents=True)
        self.book = self.root / 'books/author-example'
        self.book.mkdir(parents=True)
        self.original = self.source / 'original.pdf'
        self.original.write_bytes(b'original-source-bytes')
        self.manuscript = self.source / 'md.example/body.md'
        self.manuscript.parent.mkdir()
        self.manuscript.write_text('完整工作稿\n', encoding='utf-8')
        self.candidate = self.source / 'build.author-example/author-example.epub'
        self.candidate.parent.mkdir()
        self.candidate.write_bytes(b'unchanged-candidate-bytes')
        self.report = self.source / 'validation.author-example/epubcheck.json'
        self.report.parent.mkdir()
        self.report.write_text('{"historical":true}', encoding='utf-8')
        editorial = self.source / 'editorial.example'
        editorial.mkdir()
        self.summary = editorial / 'publication-validation.json'
        self.summary.write_text('{"candidate_sha256":"historical"}', encoding='utf-8')
        paths = [self.original, self.manuscript, self.candidate, self.report, self.summary]
        data = {'schema_version': 3, 'path_base': 'project', 'source_set_id': 'source-set',
            'source_path': self.original.relative_to(self.root).as_posix(),
            'files': [{'path': p.relative_to(self.root).as_posix(), 'sha256': digest(p)} for p in paths],
            'books': [{'book_id': 'author-example', 'book_directory': 'books/author-example',
                'markdown_directory': 'data/raw/source-set/md.example', 'editorial_directory': 'data/raw/source-set/editorial.example',
                'publication_status': {'candidate_path': self.candidate.relative_to(self.root).as_posix(),
                    'working_revision_pending_publication': 'working-revision-one'}}],
            'build_runs': [{'book_id': 'author-example', 'candidate_path': self.candidate.relative_to(self.root).as_posix(), 'sha256': digest(self.candidate)}]}
        self.manifest = self.source / 'manifest.json'
        self.manifest.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')

    def test_check_then_move_preserves_bytes_and_separates_build_history(self):
        before = {p.relative_to(self.source): p.read_bytes() for p in self.source.rglob('*') if p.is_file()}
        result = migrate_data_layout(self.root, check=True)
        self.assertEqual(result['status'], 'checked-not-migrated')
        self.assertFalse((self.root / 'data/work').exists())
        result = migrate_data_layout(self.root)
        self.assertTrue(result['all_moved_bytes_verified'])
        self.assertFalse((self.root / 'data/raw').exists())
        working = self.root / 'data/work/source-set'
        distribution = self.book / 'dist'
        self.assertEqual((working / 'original.pdf').read_bytes(), before[Path('original.pdf')])
        self.assertEqual((working / 'md.example/body.md').read_bytes(), before[Path('md.example/body.md')])
        self.assertEqual((distribution / 'author-example.epub').read_bytes(), before[Path('build.author-example/author-example.epub')])
        self.assertEqual((distribution / 'epubcheck.json').read_bytes(), before[Path('validation.author-example/epubcheck.json')])
        current = json.loads((working / 'manifest.json').read_text(encoding='utf-8'))
        self.assertEqual(current['source_path'], 'data/work/source-set/original.pdf')
        self.assertNotIn('build_runs', current)
        self.assertNotIn('candidate_path', current['books'][0]['publication_status'])
        self.assertEqual(current['books'][0]['publication_status']['working_revision_pending_publication'], 'working-revision-one')
        self.assertFalse(any(row['path'].startswith('books/author-example/dist/') for row in current['files']))
        history = json.loads((distribution / 'build-history.json').read_text(encoding='utf-8'))
        self.assertEqual(history['build_runs'][0]['candidate_path'], 'books/author-example/dist/author-example.epub')
        self.assertTrue((self.root / 'data/inbox').is_dir())
        self.assertEqual(migrate_data_layout(self.root)['status'], 'already-current')

    def test_conflict_refuses_before_any_source_move(self):
        distribution = self.book / 'dist'
        distribution.mkdir()
        occupied = distribution / 'author-example.epub'
        occupied.write_bytes(b'previous-book-build')
        original_manifest = self.manifest.read_bytes()
        with self.assertRaises(FileExistsError):
            migrate_data_layout(self.root)
        self.assertEqual(self.manifest.read_bytes(), original_manifest)
        self.assertEqual(occupied.read_bytes(), b'previous-book-build')
        self.assertFalse((self.root / 'data/work').exists())

    def test_existing_working_directory_is_not_merged(self):
        (self.root / 'data/work').mkdir()
        with self.assertRaises(FileExistsError):
            migrate_data_layout(self.root)
        self.assertTrue(self.original.is_file())

    def test_unreadable_directory_cannot_be_omitted_from_inventory(self):
        original_iterdir = Path.iterdir

        def iterdir(path):
            if path == self.manuscript.parent:
                raise PermissionError('unreadable working materials')
            return original_iterdir(path)

        with patch.object(Path, 'iterdir', iterdir):
            with self.assertRaises(PermissionError):
                migrate_data_layout(self.root)
        self.assertTrue(self.original.is_file())
        self.assertTrue(self.manuscript.is_file())
        self.assertFalse((self.root / 'data/work').exists())

    def test_interruption_before_rename_retries_only_identical_inputs(self):
        with patch.object(Path, 'rename', side_effect=PermissionError('blocked')):
            with self.assertRaises(PermissionError):
                migrate_data_layout(self.root)
        self.assertTrue(self.original.is_file())
        self.assertTrue(migrate_data_layout(self.root)['all_moved_bytes_verified'])

    def test_changed_inputs_after_interruption_are_not_moved(self):
        with patch.object(Path, 'rename', side_effect=PermissionError('blocked')):
            with self.assertRaises(PermissionError):
                migrate_data_layout(self.root)
        self.original.write_bytes(b'new-source-bytes')
        with self.assertRaisesRegex(ValueError, 'source files changed'):
            migrate_data_layout(self.root)
        self.assertFalse((self.root / 'data/work').exists())

    def test_open_legacy_parent_can_be_left_empty_after_verified_migration(self):
        original_rename = Path.rename
        original_rmdir = Path.rmdir
        legacy = self.root / 'data/raw'

        def rename(path, target):
            if path == legacy:
                raise PermissionError('parent held open')
            return original_rename(path, target)

        def rmdir(path):
            if path == legacy:
                raise PermissionError('parent held open')
            return original_rmdir(path)

        with patch.object(Path, 'rename', rename), patch.object(Path, 'rmdir', rmdir):
            result = migrate_data_layout(self.root)
            self.assertTrue(result['all_moved_bytes_verified'])
            self.assertTrue(result['legacy_empty_directory_retained'])
            self.assertEqual(list(legacy.iterdir()), [])
            receipt = json.loads((self.root / 'data/cache/layout-migration/layout-complete.json').read_text(encoding='utf-8'))
            self.assertEqual(receipt['working_files'], 6)
            self.assertEqual(migrate_data_layout(self.root)['status'], 'already-current')
        self.assertFalse(migrate_data_layout(self.root)['legacy_empty_directory_retained'])
        self.assertFalse(legacy.exists())


class IndependentBookBuildTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.book_id = 'author-example'
        self.book = initialize_book(self.root, BookMetadata(1, self.book_id, 'example', '古籍', 'zh-Hant',
            '數位整理本', 'draft', creators=(Creator('author', '作者'),)))
        (self.book / 'src/epub/images/cover.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg" width="1400" height="2100"><rect width="1400" height="2100" fill="white"/></svg>', encoding='utf-8')
        package = self.book / 'src/epub/content.opf'
        document = ET.parse(package).getroot()
        ids = {}
        for item in document.findall('opf:manifest/opf:item', NS):
            ids[item.get('id')] = 'resource-' + item.get('id')
            item.set('id', ids[item.get('id')])
        for item in document.findall('opf:spine/opf:itemref', NS):
            item.set('idref', ids[item.get('idref')])
        ET.SubElement(document.find('opf:manifest', NS), f'{{{OPF}}}item',
                      {'id': 'cover-image', 'href': 'images/cover.svg', 'media-type': 'image/svg+xml', 'properties': 'cover-image'})
        write_xml(package, document)

    def run_build(self, *extra):
        output = io.StringIO()
        with redirect_stdout(output), redirect_stderr(io.StringIO()):
            status = main(['--root', str(self.root), 'build-book', self.book_id, *extra])
        return status, json.loads(output.getvalue()) if output.getvalue() else None

    @staticmethod
    def fixture_checker(candidate, jar, report, **kwargs):
        # Synthetic output; this test does not run official EPUBCheck.
        report.write_text(json.dumps({'checker': {'checkerVersion': 'fixture', 'nFatal': 0, 'nError': 0, 'nWarning': 0}}), encoding='utf-8')
        return {'status': 'passed', 'exit_code': 0, 'report': str(report), 'report_sha256': digest(report), 'jar_sha256': 'a' * 64}

    def test_books_only_build_needs_no_data_or_manifest(self):
        status, result = self.run_build()
        self.assertEqual(status, 0)
        self.assertFalse((self.root / 'data').exists())
        self.assertEqual(result['candidate_path'], 'books/author-example/dist/author-example.epub')
        self.assertEqual(result['epubcheck']['status'], 'not-run')
        receipt = self.root / result['build_record']
        self.assertEqual(json.loads(receipt.read_text(encoding='utf-8'))['sha256'], digest(self.root / result['candidate_path']))
        self.assertEqual(self.run_build()[0], 2)

    def test_build_outputs_and_synthetic_report_are_kept_with_book(self):
        with patch('hanqing.cli.run_epubcheck', side_effect=self.fixture_checker):
            status, result = self.run_build('--epubcheck-jar', 'fixture.jar')
        self.assertEqual(status, 0)
        self.assertFalse((self.root / 'data').exists())
        self.assertTrue(result['validation_summary']['path'].startswith('books/author-example/dist/'))
        summary = json.loads((self.root / result['validation_summary']['path']).read_text(encoding='utf-8'))
        self.assertEqual(summary['full_proofreading'], 'not-recorded')
        self.assertEqual(summary['release_status'], 'not-released')
        self.assertFalse((self.book / 'editorial/publication-validation.json').exists())

    def test_other_workspaces_or_books_cannot_receive_build_output(self):
        for output in ['data/work/candidate.epub', 'books/other-book/dist/candidate.epub', '../candidate.epub']:
            with self.subTest(output=output):
                self.assertEqual(self.run_build('--output', output)[0], 2)
        self.assertFalse((self.book / 'dist').exists())

    def test_validation_rejects_changed_bytes_and_report_outside_book(self):
        with patch('hanqing.cli.run_epubcheck', side_effect=self.fixture_checker):
            _, result = self.run_build('--epubcheck-jar', 'fixture.jar')
        candidate = self.root / result['candidate_path']
        checker = self.root / result['epubcheck']['report']
        result['epubcheck']['report'] = str(checker)
        before = candidate.read_bytes()
        candidate.write_bytes(before + b'changed')
        with self.assertRaisesRegex(ValueError, 'Candidate SHA-256 changed'):
            record_validation(self.root, self.book, candidate, result)
        candidate.write_bytes(before)
        result['epubcheck']['report'] = 'data/work/epubcheck.json'
        with self.assertRaisesRegex(ValueError, "this book's dist"):
            record_validation(self.root, self.book, candidate, result)


if __name__ == '__main__':
    unittest.main()
