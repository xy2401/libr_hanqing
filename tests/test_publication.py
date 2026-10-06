import hashlib
import io
import json
from contextlib import redirect_stdout
from pathlib import Path
import shutil
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile
from unittest.mock import patch

from hanqing.models import BookMetadata, Creator, Series
from hanqing.publication.assemble import accept_proposal, assemble_book, digest, tree_hashes
from hanqing.publication.markdown import convert_markdown, select_markdown
from hanqing.publication.package import build_candidate
from hanqing.publication.evidence import record_validation
from hanqing.cli import main
from hanqing.publication.xmlutil import NS, OPF, OPS, XHTML, project_path, write_xml
from hanqing.scaffold import initialize_book
from hanqing.validators.publication import check_source


class SelectionTests(unittest.TestCase):
    def test_modern_notes_are_explicitly_removed_and_original_line_numbers_retained(self):
        original = '現代前言\n\n# 原序\n\n原文（原著夾注）[^modern]\n\n### 校勘注釋\n\n[^modern]: 現代注\n'
        selected, decision = select_markdown(original, {"line_range": [3, 5], "omit_note_ids": ["modern"]})
        self.assertEqual(selected.splitlines()[2], '# 原序')
        self.assertIn('原文（原著夾注）', selected)
        self.assertNotIn('現代', selected)
        self.assertEqual(decision['removed_note_callouts'], {'modern': 1})

    def test_unresolved_notes_and_out_of_bounds_selections_fail(self):
        for selection in [{"line_range": [1, 2]}, {"line_range": [0, 1]}, {"line_range": [1, 99]}]:
            with self.subTest(selection=selection), self.assertRaises(ValueError):
                select_markdown('# 原序\n原文[^missing]\n', selection)

    def test_project_paths_reject_absolute_and_traversal_inputs(self):
        with tempfile.TemporaryDirectory() as folder:
            for value in ('../a', '/a', 'a/../b', 'C:/a', 'a\\b', 'a//b'):
                with self.subTest(value=value), self.assertRaises(ValueError):
                    project_path(Path(folder), value)


@unittest.skipUnless(shutil.which('pandoc'), 'local Pandoc is required for conversion integration tests')
class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.book_id = 'author-example'
        book = BookMetadata(1, self.book_id, 'example', '古籍', 'zh-Hant', '數位整理本', 'draft',
            creators=(Creator('author', '作者'), Creator('original-commentator', '原注者', 'commentator')),
            series=(Series('classics', '古籍系列', 2),))
        self.book = initialize_book(self.root, book)
        (self.book/'src/epub/images/cover.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg" width="1400" height="2100"><rect width="1400" height="2100" fill="white"/></svg>', encoding='utf-8')
        self.md = self.book/'md/body.md'
        self.md.write_text('# 原篇\n\n§1 原著夾注（原注）[^modern]\n\n"Wrong example": He have books... -- preserve.\n\n| 中文 | English |\n| --- | --- |\n| 字母 | Alphabet |\n\n1. Example<br>原例\n2. Second example\n\n### 校勘注釋\n\n[^modern]: 現代注釋\n', encoding='utf-8')
        self.manifest = self.root/'data/work/source-set/manifest.json'
        self.manifest.parent.mkdir(parents=True)
        path = self.md.relative_to(self.root).as_posix()
        data = {"schema_version": 3, "path_base": "project", "files": [{"path": path, "sha256": digest(self.md)}], "books": [{"book_id": self.book_id, "book_directory": self.book.relative_to(self.root).as_posix(), "markdown_order": [{"path": path}], "publication_policy": {"modern_notes": "exclude"}, "publication_plan": [{"chapter_id": "chapter-one", "title": "原篇", "markdown_path": path, "markdown_sha256": digest(self.md), "line_range": [1, 12], "omit_note_ids": ["modern"], "epub_type": "chapter"}]}]}
        self.manifest.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')

    def assemble(self):
        result = assemble_book(self.root, self.manifest, self.book_id)
        return Path(result['proposal'])

    def test_proposal_preserves_baseline_and_canonical_source_with_semantic_structure(self):
        original_md = self.md.read_bytes()
        before = tree_hashes(self.book/'src')
        proposal = self.assemble()
        self.assertEqual(self.md.read_bytes(), original_md)
        self.assertEqual(tree_hashes(self.book/'src'), before)
        xhtml = ET.parse(proposal/'src/epub/text/chapter-one.xhtml')
        text = ''.join(xhtml.getroot().itertext())
        self.assertIn('"Wrong example": He have books... -- preserve.', text)
        self.assertIn('原著夾注（原注）', text)
        self.assertNotIn('現代注釋', text)
        self.assertNotIn('data-wrapper', (proposal/'src/epub/text/chapter-one.xhtml').read_text(encoding='utf-8'))
        self.assertEqual(len(xhtml.findall('.//h:table', NS)), 1)
        self.assertIsNotNone(xhtml.find('.//h:br', NS))
        self.assertIsNotNone(xhtml.find(".//h:span[@lang='en']", NS))
        rows = [json.loads(line) for line in (proposal/'source-map.jsonl').read_text(encoding='utf-8').splitlines()]
        self.assertTrue(all(1 <= r['markdown_lines'][0] <= r['markdown_lines'][1] <= 12 for r in rows))
        with self.assertRaises(FileExistsError):
            self.assemble()

    def test_changed_baseline_and_canonical_edits_block_conversion_acceptance(self):
        self.assemble()
        self.md.write_text(self.md.read_text(encoding='utf-8') + '\n', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'baseline changed'):
            accept_proposal(self.root, self.manifest, self.book_id, reviewer='editor')
        self.assertFalse((self.book/'src/epub/text/chapter-one.xhtml').exists())

    def test_source_edit_since_assembly_is_not_overwritten(self):
        self.assemble()
        path = self.book/'src/epub/text/titlepage.xhtml'
        path.write_text('人工校勘成果', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'source changed'):
            accept_proposal(self.root, self.manifest, self.book_id, reviewer='editor')
        self.assertEqual(path.read_text(encoding='utf-8'), '人工校勘成果')

    def test_baseline_hash_mismatch_blocks_assembly(self):
        self.md.write_text('# 改變\n', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'SHA-256 changed'):
            self.assemble()

    def use_raw_working_markdown(self):
        raw = self.manifest.parent / 'md.example'
        raw.mkdir()
        self.md.rename(raw / self.md.name)
        self.md = raw / self.md.name
        data = json.loads(self.manifest.read_text(encoding='utf-8'))
        path = self.md.relative_to(self.root).as_posix()
        data['files'][0]['path'] = path
        relation = data['books'][0]
        relation['markdown_directory'] = raw.relative_to(self.root).as_posix()
        relation['markdown_order'][0]['path'] = path
        relation['publication_plan'][0]['markdown_path'] = path
        self.manifest.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')

    def test_raw_working_markdown_is_retained_and_accepted_mapping_uses_git_snapshot(self):
        self.use_raw_working_markdown()
        before = self.md.read_bytes()
        self.accepted_source()
        snapshot = self.book / 'md/body.md'
        self.assertEqual(snapshot.read_bytes(), before)
        self.assertEqual(self.md.read_bytes(), before)
        rows = [json.loads(line) for line in (self.book/'editorial/source-map.jsonl').read_text(encoding='utf-8').splitlines()]
        self.assertTrue(all(row['markdown_path'] == snapshot.relative_to(self.root).as_posix() for row in rows))
        accepted = json.loads((self.book/'editorial/conversion-review.json').read_text(encoding='utf-8'))
        self.assertEqual(accepted['chapters'][0]['markdown_path'], snapshot.relative_to(self.root).as_posix())
        self.md.write_text('后续工作稿', encoding='utf-8')
        candidate, result = self.fixture_candidate(self.book/'src', 'raw')
        record_validation(self.root, self.book, candidate, result)
        self.assertEqual(snapshot.read_bytes(), before)

    def test_raw_acceptance_refuses_overwriting_an_existing_different_book_snapshot(self):
        self.use_raw_working_markdown()
        self.assemble()
        snapshot = self.book / 'md/body.md'
        snapshot.write_text('已有快照', encoding='utf-8')
        before = tree_hashes(self.book/'src')
        with self.assertRaisesRegex(FileExistsError, 'Existing book snapshot'):
            accept_proposal(self.root, self.manifest, self.book_id, reviewer='editor')
        self.assertEqual(tree_hashes(self.book/'src'), before)
        self.assertEqual(snapshot.read_text(encoding='utf-8'), '已有快照')

    def test_raw_markdown_from_a_different_source_set_is_rejected(self):
        self.use_raw_working_markdown()
        data = json.loads(self.manifest.read_text(encoding='utf-8'))
        data['books'][0]['markdown_directory'] = 'data/work/different-source/md.example'
        self.manifest.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'this source set'):
            self.assemble()

    def test_retained_original_footnotes_have_semantics_backlinks_and_mapping(self):
        fragment, rows = convert_markdown('# 原篇\n\n原文[^original]\n\n[^original]: 原著注\n', 'original-chapter')
        reference = fragment.find(".//h:a[@epub:type='noteref']", NS)
        note = fragment.find(".//h:li[@epub:type='footnote']", NS)
        back = fragment.find(".//h:a[@role='doc-backlink']", NS)
        self.assertEqual(reference.get('href'), '#' + note.get('id'))
        self.assertEqual(back.get('href'), '#' + reference.get('id'))
        self.assertTrue(any(r['element_id'] == note.get('id') and r['markdown_lines'] == [5, 5] for r in rows))

    def accepted_source(self):
        self.assemble()
        accept_proposal(self.root, self.manifest, self.book_id, reviewer='editor')
        return self.book/'src'

    def test_acceptance_preserves_prior_tree_and_separate_proofreading_status(self):
        source = self.accepted_source()
        self.assertTrue((self.manifest.parent/f'proposal.{self.book_id}/previous-src/epub/content.opf').exists())
        self.assertIn('status = "pending"', (self.manifest.parent/'editorial.example/review.toml').read_text(encoding='utf-8'))
        self.assertFalse((self.book/'editorial/review.toml').exists())
        with self.assertRaises(ValueError):
            accept_proposal(self.root, self.manifest, self.book_id, reviewer='editor')
        check_source(source)

    def test_regeneration_only_changes_a_new_proposal_and_preserves_accepted_edits(self):
        source = self.accepted_source()
        chapter = source/'epub/text/chapter-one.xhtml'
        doc = ET.parse(chapter).getroot()
        ET.SubElement(doc.find('h:body/h:section', NS), f'{{{XHTML}}}p').text = '人工校勘成果'
        write_xml(chapter, doc)
        before = tree_hashes(source)
        old = self.manifest.parent/f'proposal.{self.book_id}'
        old.rename(self.manifest.parent/'accepted-proposal')
        proposal = self.assemble()
        self.assertEqual(tree_hashes(source), before)
        self.assertNotIn('人工校勘成果', (proposal/'src/epub/text/chapter-one.xhtml').read_text(encoding='utf-8'))
        with self.assertRaisesRegex(ValueError, 'Already accepted'):
            accept_proposal(self.root, self.manifest, self.book_id, reviewer='editor')

    def test_package_only_src_is_deterministic_and_has_ocf_mimetype_first(self):
        source = self.accepted_source()
        first = self.root/'candidate.epub'; second = self.root/'candidate-2.epub'
        report = build_candidate(source, first)
        build_candidate(source, second)
        self.assertEqual(first.read_bytes(), second.read_bytes())
        self.assertEqual(report['sha256'], digest(first))
        with zipfile.ZipFile(first) as archive:
            entry = archive.infolist()[0]
            self.assertEqual((entry.filename, entry.compress_type, entry.extra), ('mimetype', zipfile.ZIP_STORED, b''))
            self.assertEqual(archive.read('mimetype'), b'application/epub+zip')
            self.assertFalse(any(name.endswith('.md') or 'editorial' in name for name in archive.namelist()))
        with self.assertRaises(ValueError):
            build_candidate(source, first)

    def test_original_contributor_roles_and_series_are_preserved(self):
        proposal = self.assemble()
        package = ET.parse(proposal/'src/epub/content.opf')
        self.assertEqual(package.find('opf:metadata/dc:contributor', NS).text, '原注者')
        self.assertEqual(package.find("opf:metadata/opf:meta[@property='role'][@refines='#metadata-creator-2']", NS).text, 'cwt')
        self.assertEqual(package.find("opf:metadata/opf:meta[@property='belongs-to-collection']", NS).text, '古籍系列')

    def fixture_checker_result(self, candidate, jar, report, **kwargs):
        # Synthetic checker metadata for unit tests; real EPUBCheck is separately run on the books.
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps({'checker': {'checkerVersion': 'fixture', 'nFatal': 0, 'nError': 0, 'nWarning': 0}}), encoding='utf-8')
        return {'status': 'passed', 'exit_code': 0, 'report': str(report), 'report_sha256': digest(report), 'jar_sha256': 'a' * 64}

    def fixture_candidate(self, source, name):
        candidate = self.book/'dist'/f'{name}.epub'
        result = build_candidate(source, candidate)
        result['epubcheck'] = self.fixture_checker_result(candidate, None, candidate.with_suffix('.epubcheck.json'))
        return candidate, result

    def test_validation_summary_archives_old_bytes_and_resets_reader_on_new_candidate(self):
        source = self.accepted_source()
        candidate, result = self.fixture_candidate(source, 'first')
        record_validation(self.root, self.book, candidate, result)
        summary = candidate.with_suffix('.validation.json')
        self.assertFalse((self.book/'editorial/publication-validation.json').exists())
        previous = json.loads(summary.read_text(encoding='utf-8'))
        previous['reader_acceptance'] = {'status': 'passed', 'reader': 'fixture-reader'}
        summary.write_text(json.dumps(previous), encoding='utf-8')
        old_bytes = summary.read_bytes()
        record = record_validation(self.root, self.book, candidate, result)
        self.assertEqual((self.root/record['previous_summary']).read_bytes(), old_bytes)
        self.assertEqual(json.loads(summary.read_text(encoding='utf-8'))['reader_acceptance']['status'], 'passed')
        chapter = source/'epub/text/chapter-one.xhtml'
        doc = ET.parse(chapter).getroot()
        ET.SubElement(doc.find('h:body/h:section', NS), f'{{{XHTML}}}p').text = '另一次正文修订'
        write_xml(chapter, doc)
        candidate, result = self.fixture_candidate(source, 'second')
        record_validation(self.root, self.book, candidate, result)
        final = json.loads(candidate.with_suffix('.validation.json').read_text(encoding='utf-8'))
        self.assertEqual(final['reader_acceptance']['status'], 'pending')
        self.assertEqual(final['full_proofreading'], 'not-recorded')
        self.assertEqual(final['release_status'], 'not-released')

    def test_stale_candidate_report_source_or_mapping_cannot_replace_summary(self):
        source = self.accepted_source()
        candidate, result = self.fixture_candidate(source, 'first')
        record_validation(self.root, self.book, candidate, result)
        summary = candidate.with_suffix('.validation.json')
        original_summary = summary.read_bytes()
        checker = Path(result['epubcheck']['report'])
        source_file = source/'epub/text/chapter-one.xhtml'
        mapping = self.book/'editorial/source-map.jsonl'
        for path in [candidate, checker, source_file, self.md, mapping]:
            with self.subTest(path=path.name):
                before = path.read_bytes()
                if path == mapping:
                    rows = [json.loads(line) for line in before.decode('utf-8').splitlines()]
                    rows[0]['element_id'] = 'missing-anchor'
                    path.write_text(''.join(json.dumps(row) + '\n' for row in rows), encoding='utf-8')
                else:
                    path.write_bytes(before + b'\n')
                with self.assertRaises(ValueError):
                    record_validation(self.root, self.book, candidate, result)
                self.assertEqual(summary.read_bytes(), original_summary)
                path.write_bytes(before)

    def test_build_cli_saves_independent_book_receipt_without_changing_work_manifest(self):
        self.accepted_source()
        before = self.manifest.read_bytes()
        with patch('hanqing.cli.run_epubcheck', side_effect=self.fixture_checker_result), redirect_stdout(io.StringIO()):
            status = main(['--root', str(self.root), 'build-book', self.book_id, '--epubcheck-jar', 'fixture.jar'])
        self.assertEqual(status, 0)
        self.assertEqual(self.manifest.read_bytes(), before)
        receipt = self.book/'dist'/f'{self.book_id}.build.json'
        record = json.loads(receipt.read_text(encoding='utf-8'))['validation_summary']
        self.assertTrue(record['path'].startswith('books/author-example/dist/'))
        self.assertFalse((self.book/'editorial/publication-validation.json').exists())
        self.assertEqual(digest(self.root/record['path']), record['sha256'])
        self.assertEqual(json.loads((self.root/record['path']).read_text(encoding='utf-8'))['markdown_mapping']['anchors_and_baseline_hashes'], 'passed')

    def test_bad_global_id_fragment_nonpublication_and_nav_spine_are_rejected(self):
        source = self.accepted_source()
        chapter = source/'epub/text/chapter-one.xhtml'
        original = chapter.read_bytes()
        for mutation, message in [
            (lambda doc: doc.find('h:body/h:section', NS).set('id', 'titlepage'), 'globally unique'),
            (lambda doc: ET.SubElement(doc.find('h:body/h:section', NS), f'{{{XHTML}}}a', {'href': '#absent'}), 'Broken fragment'),
        ]:
            with self.subTest(message=message):
                doc = ET.fromstring(original); mutation(doc); write_xml(chapter, doc)
                with self.assertRaisesRegex(ValueError, message): check_source(source)
                chapter.write_bytes(original)
        unexpected = source/'accidental.md'; unexpected.write_text('底本', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'Non-publication'): check_source(source)
        unexpected.unlink()
        opf = source/'epub/content.opf'; doc = ET.parse(opf).getroot(); spine = doc.find('opf:spine', NS)
        nav_id = next(n.get('id') for n in doc.findall('opf:manifest/opf:item', NS) if n.get('properties') == 'nav')
        spine.remove(next(n for n in spine if n.get('idref') == nav_id)); write_xml(opf, doc)
        with self.assertRaisesRegex(ValueError, 'not a spine item'): check_source(source)


if __name__ == '__main__':
    unittest.main()
