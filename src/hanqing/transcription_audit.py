"""Check the bytes and page coverage of explicitly assigned draft regions."""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from .ingest import digest, _save_manifest
from .models import validate_id
from .publication.xmlutil import project_path
from .transcription import validate_page, markdown_page, _write_preserved


def audit_transcription_task(root: Path, manifest_path: Path, task_id: str):
    root = root.resolve()
    task_id = validate_id(task_id)
    manifest_path = project_path(root, manifest_path.resolve().relative_to(root).as_posix())
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    source_set = validate_id(manifest['source_set_id'])
    if (manifest.get('schema_version') != 3 or manifest.get('path_base') != 'project'
            or manifest_path != root / f'data/work/{source_set}/manifest.json'):
        raise ValueError('Requires the source set work manifest v3')
    if digest(project_path(root, manifest['source_path'])) != manifest['source_sha256']:
        raise ValueError('Original source bytes changed')
    task = next((t for t in manifest.get('recognition_tasks', []) if t['task_id'] == task_id), None)
    if task is None or task.get('method') != 'assistant-direct-multimodal':
        raise ValueError('Supply an explicitly defined assistant visual transcription task')
    scope = task['scope']
    first, last = scope['first_physical_page'], scope['last_physical_page']
    if type(first) is not int or type(last) is not int or not 1 <= first <= last:
        raise ValueError('Invalid task scope')
    runs = {r['run_id']: r for r in manifest['recognition_runs']}
    unpacked = {p['physical_page']: p for p in manifest['pdf_unpack']['pages']}
    inventory = {f['path']: f for f in manifest['files']}
    verified = {}

    def verify_file(path, sha):
        if path not in verified:
            verified[path] = digest(project_path(root, path))
        if verified[path] != sha:
            raise ValueError(f'Actual file hash differs: {path}')

    pages, region_rows, expected_next = [], [], first
    for region in task['regions']:
        if region['first'] != expected_next or region['last'] < region['first'] or region['last'] > last:
            raise ValueError('Regions must explicitly and consecutively cover the task scope')
        expected_next = region['last'] + 1
        run = runs.get(region.get('run_id'))
        if run is None:
            raise ValueError('Each task region requires its explicit run_id')
        run_scope = run['config']['scope']
        if (run_scope['first_physical_page'] != region['first'] or run_scope['last_physical_page'] != region['last']
                or run['source_sha256'] != manifest['source_sha256']
                or run['config']['method'] != task['method']):
            raise ValueError('Region run scope, source or method differs')
        wanted = list(range(region['first'], region['last'] + 1))
        if ([p['physical_page'] for p in run['pages']] != wanted or run.get('completed_pages') != wanted
                or run.get('status') != 'scoped-transcription-draft-complete'):
            raise ValueError('Region has missing, duplicate, unordered or incomplete draft pages')
        verify_file(run['page_map'], run['page_map_sha256'])
        for input_record in run['input_records']:
            verify_file(input_record['path'], input_record['sha256'])
        for page in run['pages']:
            text = page['transcription']
            validate_page(text)
            number = page['physical_page']
            if text['source_id'] != manifest['source_id'] or text['physical_page'] != number:
                raise ValueError('Transcription page/source differs')
            image = next((i for i in unpacked.get(number, {}).get('images', []) if i['path'] == page['image_path']), None)
            if image is None:
                image = next((i for i in manifest.get('pdf_renderings', [])
                              if i['physical_page'] == number and i['path'] == page['image_path']), None)
                if (image is None or image.get('kind') != 'pdf-full-page-render'
                        or image.get('source_path') != manifest['source_path']
                        or image.get('source_sha256') != manifest['source_sha256']
                        or image.get('parameters', {}).get('additional_crop_lbrt') != [0, 0, 0, 0]
                        or image.get('parameters', {}).get('additional_rotation') != 0):
                    raise ValueError('Rendered page/source association differs')
            if image['sha256'] != page['image_sha256']:
                raise ValueError('Page image reference hash differs')
            verify_file(page['image_path'], page['image_sha256'])
            verify_file(page['markdown_path'], page['markdown_sha256'])
            if (page.get('status') != 'saved-unproofread-draft'
                    or hashlib.sha256(markdown_page(text).encode('utf-8')).hexdigest() != page['markdown_sha256']
                    or inventory.get(page['markdown_path'], {}).get('sha256') != page['markdown_sha256']):
                raise ValueError('Saved text, working inventory or draft status differs')
            for crop in page.get('visual_preparation', []):
                if crop['source_sha256'] != page['image_sha256']:
                    raise ValueError('Crop source differs')
                verify_file(crop['path'], crop['sha256'])
                verify_file(crop['record_path'], crop['record_sha256'])
            pages.append(page)
        region_rows.append({'label': region['label'], 'first': region['first'], 'last': region['last'],
                            'run_id': run['run_id'], 'page_count': len(wanted),
                            'markdown_directory': run['config']['markdown_directory'],
                            'page_map': run['page_map'], 'page_map_sha256': run['page_map_sha256']})
    if expected_next != last + 1:
        raise ValueError('Regions leave a gap at the task end')
    lines = ['# 整卷初录检查报告', '', '状态：逐页初录已保存，待校勘；未接受为出版正文。', '',
             f'物理页域：{first}–{last}，共 {len(pages)} 页。',
             f'原件 SHA-256：`{manifest["source_sha256"]}`。', '',
             '本次只核验原件、逐页稿、页图/渲染图、输入历史、页码表和裁切记录的实际哈希，以及页序和结构。',
             '文字由助手逐页视读录入；本检查不识别图片，不证明每个字准确或没有漏录。',
             '坐标是人工目测的整页归一化框。现代附加材料和注释仍留在工作稿，出版取舍尚未接受。', '',
             '| 区域 | 物理页 | 页数 | 工作稿目录 |', '| --- | --- | --- | --- |']
    for row in region_rows:
        lines.append(f'| {row["label"]} | {row["first"]}–{row["last"]} | {row["page_count"]} | `{row["markdown_directory"]}` |')
    lines.extend(['', '## 逐页复核标记', '', '以下保留初录时的疑点、跨页边界及区块性质说明，不按条数推断错误数。', ''])
    marked = []
    for page in pages:
        notes = list(page['transcription']['warnings'])
        for block in page['transcription']['blocks']:
            notes.extend(f'{block["id"]}：{note}' for note in block['uncertainties'])
        if notes:
            marked.append(page['physical_page'])
            lines.extend([f'### 物理页 {page["physical_page"]}', '',
                          f'[{Path(page["markdown_path"]).name}](../{Path(page["markdown_path"]).parent.name}/{Path(page["markdown_path"]).name})', ''])
            lines.extend('- ' + note.replace('\n', ' ') for note in notes)
            lines.append('')
    report = project_path(root, f'data/work/{source_set}/editorial.{task_id}/transcription-report.md')
    report_sha = _write_preserved(root, report, '\n'.join(lines) + '\n')
    relative = report.relative_to(root).as_posix()
    entry = next((f for f in manifest['files'] if f['path'] == relative), None)
    if entry is None:
        manifest['files'].append({'path': relative, 'kind': 'transcription-task-audit', 'sha256': report_sha,
                                  'original_sha256': report_sha})
    else:
        entry['sha256'] = report_sha
    result = {'status': 'initial-transcription-draft-complete', 'checked_at': datetime.now(timezone.utc).isoformat(),
              'method': 'file-hash-and-recorded-page-coverage', 'source_sha256': manifest['source_sha256'],
              'page_count': len(pages), 'completed_pages': [p['physical_page'] for p in pages],
              'regions': region_rows, 'report_path': relative, 'report_sha256': report_sha,
              'pages_with_review_markers': marked, 'proofreading': 'not-performed',
              'publication_acceptance': 'not-performed', 'visual_completeness_review': 'not-performed'}
    if task.get('audit'):
        task.setdefault('audit_history', []).append(task['audit'])
    task.update(status=result['status'], completed_pages=result['completed_pages'], audit=result)
    _save_manifest(root, manifest_path, manifest)
    return result
