"""Save the assistant's own visual transcriptions; never recognize images here."""

from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path

from . import __version__
from .ingest import digest, _save_manifest
from .models import validate_id
from .publication.xmlutil import project_path

KINDS = {'heading', 'main', 'annotation', 'page-number', 'seal', 'illustration', 'other'}


def validate_page(page):
    required = {'source_id', 'physical_page', 'printed_page_label', 'blocks', 'warnings'}
    if not isinstance(page, dict) or set(page) != required:
        raise ValueError('Page fields must match page-transcription schema v1')
    validate_id(page['source_id'])
    if type(page['physical_page']) is not int or page['physical_page'] < 1:
        raise ValueError('Invalid physical page')
    if not isinstance(page['printed_page_label'], str):
        raise ValueError('Printed page label must be a string')
    if not isinstance(page['warnings'], list) or any(not isinstance(v, str) for v in page['warnings']):
        raise ValueError('Warnings must be strings')
    if not isinstance(page['blocks'], list):
        raise ValueError('Blocks must be an ordered array')
    ids = set()
    for order, block in enumerate(page['blocks'], 1):
        if set(block) != {'id', 'kind', 'reading_order', 'text', 'bbox', 'uncertainties'}:
            raise ValueError('Block fields must match schema v1')
        if not isinstance(block['id'], str) or not block['id'] or block['id'] in ids:
            raise ValueError('Block IDs must be nonempty and unique')
        ids.add(block['id'])
        if block['kind'] not in KINDS or type(block['reading_order']) is not int or block['reading_order'] != order:
            raise ValueError('Invalid kind or nonsequential reading order')
        if not isinstance(block['text'], str):
            raise ValueError('Block text must be a string')
        box = block['bbox']
        if not isinstance(box, list) or len(box) != 4 or any(
            type(v) not in (int, float) or not math.isfinite(v) or not 0 <= v <= 1 for v in box
        ) or box[0] > box[2] or box[1] > box[3]:
            raise ValueError('Invalid normalized bounding box')
        if not isinstance(block['uncertainties'], list) or any(not isinstance(v, str) for v in block['uncertainties']):
            raise ValueError('Uncertainties must be strings')


def markdown_page(page):
    lines = ['<!-- 待校勘看图转录；物理页 %s；印刷页码 %s；保留原页标点与注号 -->' % (
        page['physical_page'], page['printed_page_label']), '']
    for block in page['blocks']:
        lines.append('<!-- ' + json.dumps({'block': block['id'], 'kind': block['kind']}, ensure_ascii=False) + ' -->')
        lines.extend([('## ' if block['kind'] == 'heading' else '') + block['text'], ''])
    return '\n'.join(lines)


def _write_preserved(root, path, content):
    encoded = content.encode('utf-8')
    sha = hashlib.sha256(encoded).hexdigest()
    if path.exists():
        old = path.read_bytes()
        if old == encoded:
            return sha
        archive = project_path(root, f'data/cache/transcription-history/{hashlib.sha256(old).hexdigest()}.md')
        archive.parent.mkdir(parents=True, exist_ok=True)
        if archive.exists() and archive.read_bytes() != old:
            raise ValueError('Transcription history collision')
        if not archive.exists():
            archive.write_bytes(old)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encoded)
    if digest(path) != sha:
        raise ValueError('Saved transcription hash differs')
    return sha


def record_transcriptions(root: Path, input_path: Path, *, revision_id=None, revision_reason=None,
                          revision_method='assistant-direct-multimodal'):
    """Validate supplied text and hashes, then checkpoint one saved page at a time."""
    root = root.resolve()
    input_path = project_path(root, input_path.resolve().relative_to(root).as_posix())
    data = json.loads(input_path.read_text(encoding='utf-8'))
    if revision_id is not None:
        validate_id(revision_id)
        if not isinstance(revision_reason, str) or not revision_reason.strip():
            raise ValueError('Explicit draft revision requires a reason')
    if revision_method not in {'assistant-direct-multimodal', 'existing-markdown-context'}:
        raise ValueError('Unsupported draft revision method')
    if revision_method == 'existing-markdown-context' and revision_id is None:
        raise ValueError('Text revision requires an explicit revision ID')
    scope = data.get('scope', {})
    first, last = scope.get('first_physical_page'), scope.get('last_physical_page')
    if type(first) is not int or type(last) is not int or not 1 <= first <= last:
        raise ValueError('Supply a valid physical-page scope')
    if data.get('schema_version') != 1 or data.get('method') != 'assistant-direct-multimodal':
        raise ValueError('Only explicitly supplied assistant visual transcription records are accepted')
    source_set = validate_id(data['source_set_id'])
    directory = project_path(root, f'data/work/{source_set}')
    manifest_path = directory / 'manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    if manifest.get('schema_version') != 3 or manifest.get('path_base') != 'project':
        raise ValueError('Requires the project-relative work manifest v3')
    if manifest['source_set_id'] != source_set or manifest['source_sha256'] != data['source_sha256']:
        raise ValueError('Source identity or expected hash changed')
    if digest(project_path(root, manifest['source_path'])) != manifest['source_sha256']:
        raise ValueError('Original source bytes changed')
    output = project_path(root, data['markdown_directory'])
    if output.parent != directory or not output.name.startswith('md.'):
        raise ValueError('Markdown stays directly in this source set md.<work> directory')
    validate_id(output.name[3:])
    run_id = validate_id(data['run_id'])
    prompt = project_path(root, 'src/hanqing/prompts/transcribe-page-v1.txt')
    schema = project_path(root, 'schemas/page-transcription.schema.json')
    config = {key: data.get(key) for key in ('method', 'assistant', 'model', 'markdown_directory', 'scope', 'notes')}
    config.update(prompt_sha256=digest(prompt), prompt_version='transcribe-page-v1',
                  schema_version=1, schema_sha256=digest(schema), image_processing='original-image-and-recorded-visual-crops')
    if not isinstance(data['pages'], list) or not 0 < len(data['pages']) <= 1000:
        raise ValueError('Supply 1 to 1000 explicitly transcribed pages')
    runs = manifest.setdefault('recognition_runs', [])
    run = next((r for r in runs if r['run_id'] == run_id), None)
    if run is None:
        run = {'run_id': run_id, 'source_id': manifest['source_id'], 'source_sha256': manifest['source_sha256'],
               'program_version': __version__, 'config': config, 'started_at': datetime.now(timezone.utc).isoformat(),
               'status': 'partial-draft', 'pages': [], 'errors': []}
        runs.append(run)
    elif run['config'] != config or run['source_sha256'] != manifest['source_sha256']:
        raise ValueError('Run inputs/configuration changed; use a new run ID')
    unpacked = {p['physical_page']: p for p in manifest['pdf_unpack']['pages']}
    seen = set()
    prepared = []
    # Preflight every supplied page before writing any Markdown.
    for supplied in data['pages']:
        page = supplied['transcription']
        validate_page(page)
        number = page['physical_page']
        if not first <= number <= last:
            raise ValueError('Transcription page is outside the declared scope')
        if number in seen or page['source_id'] != manifest['source_id']:
            raise ValueError('Duplicate page or mismatched source')
        seen.add(number)
        image_path = project_path(root, supplied['image_path'])
        images = unpacked.get(number, {}).get('images', [])
        image = next((i for i in images if i['path'] == supplied['image_path']), None)
        image_origin = {'kind': 'embedded-image-stream'}
        if image is None:
            image = next((i for i in manifest.get('pdf_renderings', [])
                          if i['physical_page'] == number and i['path'] == supplied['image_path']), None)
            if image is not None:
                if (image.get('schema_version') != 1 or image.get('kind') != 'pdf-full-page-render'
                        or image.get('source_path') != manifest['source_path']
                        or image.get('source_sha256') != manifest['source_sha256']
                        or image.get('parameters', {}).get('additional_crop_lbrt') != [0, 0, 0, 0]
                        or image.get('parameters', {}).get('additional_rotation') != 0):
                    raise ValueError('Rendered image source or full-page parameters differ')
                image_origin = dict(image)
        if image is None or image['sha256'] != supplied['image_sha256'] or digest(image_path) != image['sha256']:
            raise ValueError('Image/page association or actual image hash differs')
        for crop in supplied.get('visual_preparation', []):
            if crop['source_sha256'] != image['sha256'] or digest(project_path(root, crop['path'])) != crop['sha256']:
                raise ValueError('Visual crop source or bytes differ')
            if digest(project_path(root, crop['record_path'])) != crop['record_sha256']:
                raise ValueError('Visual preparation coordinate record differs')
        path = project_path(root, f"{data['markdown_directory']}/page-{number:04d}.md")
        content = markdown_page(page)
        sha = hashlib.sha256(content.encode('utf-8')).hexdigest()
        previous = next((p for p in run['pages'] if p['physical_page'] == number), None)
        changed = previous and (previous['transcription'] != page or previous['markdown_sha256'] != sha)
        if changed and revision_id is None:
            raise ValueError('Completed transcription differs; preserve it and make an editorial revision')
        expected = previous['markdown_sha256'] if changed else sha
        if path.exists() and digest(path) != expected:
            raise ValueError('Existing Markdown differs; refusing to overwrite')
        if previous and not path.exists():
            raise ValueError('Recorded Markdown is missing')
        if not previous:
            existing = next((f for f in manifest['files'] if f['path'] == path.relative_to(root).as_posix()), None)
            if existing and (existing['sha256'] != sha or existing.get('source_image') != supplied['image_path']):
                raise ValueError('Existing file inventory differs; cannot reuse the draft')
        if changed:
            snapshot = path.with_name(f'{path.stem}.{revision_id}.original.md')
            if snapshot.exists() and digest(snapshot) != expected:
                raise ValueError('Revision snapshot differs; use a new revision ID')
            if revision_method == 'existing-markdown-context':
                evidence = supplied.get('text_evidence', [])
                if not evidence:
                    raise ValueError('Text revision requires current Markdown evidence')
                for reference in evidence:
                    evidence_path = project_path(root, reference['path'])
                    registered = next((f for f in manifest['files'] if f['path'] == reference['path']), None)
                    if (not evidence_path.is_relative_to(directory) or evidence_path.suffix != '.md'
                            or evidence_path.name.endswith('.original.md') or registered is None
                            or registered['sha256'] != reference['sha256'] or digest(evidence_path) != reference['sha256']
                            or not reference.get('quote') or reference['quote'] not in evidence_path.read_text(encoding='utf-8')):
                        raise ValueError('Current text evidence path, hash or quote differs')
        prepared.append((supplied, page, path, content, sha, previous, image_origin))
    input_sha = digest(input_path)
    input_archive = project_path(root, f'data/cache/transcription-history/{input_sha}.json')
    input_archive.parent.mkdir(parents=True, exist_ok=True)
    if input_archive.exists() and input_archive.read_bytes() != input_path.read_bytes():
        raise ValueError('Input record archive collision')
    if not input_archive.exists():
        input_archive.write_bytes(input_path.read_bytes())
    input_ref = {'path': input_archive.relative_to(root).as_posix(), 'sha256': input_sha}
    if input_ref not in run.setdefault('input_records', []):
        run['input_records'].append(input_ref)
    for supplied, page, path, content, sha, previous, image_origin in prepared:
        if previous and previous['transcription'] == page:
            continue
        revision = None
        if previous:
            snapshot = path.with_name(f'{path.stem}.{revision_id}.original.md')
            if not snapshot.exists():
                snapshot.write_bytes(path.read_bytes())
            if digest(snapshot) != previous['markdown_sha256']:
                raise ValueError('Revision snapshot hash differs')
            revision = {'revision_id': revision_id, 'reason': revision_reason,
                        'method': revision_method,
                        'previous_snapshot': snapshot.relative_to(root).as_posix(),
                        'previous_sha256': previous['markdown_sha256'],
                        'previous_record': {k: v for k, v in previous.items() if k != 'revisions'},
                        'acceptance': 'unproofread-working-draft-only'}
            if revision_method == 'existing-markdown-context':
                revision['text_evidence'] = [{**reference, **({'input_snapshot': snapshot.relative_to(root).as_posix()}
                    if reference['path'] == path.relative_to(root).as_posix() else {})}
                    for reference in supplied['text_evidence']]
            if not any(f['path'] == revision['previous_snapshot'] for f in manifest['files']):
                manifest['files'].append({'path': revision['previous_snapshot'],
                                          'kind': 'transcription-revision-snapshot',
                                          'sha256': revision['previous_sha256']})
        _write_preserved(root, path, content)
        relative = path.relative_to(root).as_posix()
        entry = {'path': relative, 'kind': 'assistant-transcription-markdown',
                                  'sha256': sha, 'original_sha256': sha, 'source_id': manifest['source_id'],
                                  'physical_page': page['physical_page'], 'source_image': supplied['image_path'],
                                  'source_image_sha256': supplied['image_sha256'], 'status': 'unproofread-draft'}
        if previous:
            file_entry = next(f for f in manifest['files'] if f['path'] == relative)
            file_entry['sha256'] = sha
            file_entry.setdefault('revisions', []).append(revision)
        elif not any(f['path'] == relative for f in manifest['files']):
            manifest['files'].append(entry)
        saved = {'physical_page': page['physical_page'], 'image_path': supplied['image_path'],
                             'image_sha256': supplied['image_sha256'], 'markdown_path': relative,
                             'markdown_sha256': sha, 'status': 'saved-unproofread-draft', 'transcription': page,
                             'visual_preparation': supplied.get('visual_preparation', [])}
        saved['image_origin'] = image_origin
        if previous:
            saved['revisions'] = previous.get('revisions', []) + [revision]
            run['pages'][run['pages'].index(previous)] = saved
            for other in runs:
                if other is run:
                    continue
                for old_page in other['pages']:
                    if old_page['markdown_path'] == relative and old_page['markdown_sha256'] == previous['markdown_sha256']:
                        old_page['markdown_previous_path'] = relative
                        old_page['markdown_path'] = revision['previous_snapshot']
                        other['current_input_status'] = 'historical-after-working-revision'
            for task in manifest.get('recognition_tasks', []):
                if any(region.get('run_id') == run_id for region in task.get('regions', [])) and task.get('audit'):
                    task['audit']['current_input_status'] = 'historical-after-working-revision'
        else:
            original = next((r for r in runs if r is not run and any(
                p['markdown_path'] == relative and p['markdown_sha256'] == sha for p in r['pages'])), None)
            if original:
                saved['reused_from_run_id'] = original['run_id']
            run['pages'].append(saved)
        run['pages'].sort(key=lambda p: p['physical_page'])
        run['completed_pages'] = [p['physical_page'] for p in run['pages']]
        run['last_saved_at'] = datetime.now(timezone.utc).isoformat()
        _save_manifest(root, manifest_path, manifest)
    mapping = ['# 逐页转录映射（待校勘）', '', '仅记录已保存的本轮页稿；印刷页码照图录入。区块坐标为人工目测归一化框。', '',
               '| 物理页 | 印刷页码 | Markdown | SHA-256 |', '| --- | --- | --- | --- |']
    for p in run['pages']:
        mapping.append(f"| {p['physical_page']} | {p['transcription']['printed_page_label']} | {Path(p['markdown_path']).name} | {p['markdown_sha256']} |")
    map_path = output / 'page-map.md'
    old_map_sha = digest(map_path) if map_path.exists() else None
    map_sha = _write_preserved(root, map_path, '\n'.join(mapping) + '\n')
    relative = map_path.relative_to(root).as_posix()
    if old_map_sha and old_map_sha != map_sha:
        for other in runs:
            if other is not run and other.get('page_map') == relative and other.get('page_map_sha256') == old_map_sha:
                other['page_map_previous_path'] = relative
                other['page_map'] = f'data/cache/transcription-history/{old_map_sha}.md'
    entry = next((f for f in manifest['files'] if f['path'] == relative), None)
    if entry is None:
        manifest['files'].append({'path': relative, 'kind': 'transcription-page-map', 'sha256': map_sha, 'original_sha256': map_sha})
    else:
        entry['sha256'] = map_sha
    run.update(page_map=relative, page_map_sha256=map_sha)
    if set(run['completed_pages']) == set(range(first, last + 1)):
        run['status'] = 'scoped-transcription-draft-complete'
    _save_manifest(root, manifest_path, manifest)
    return {'run_id': run_id, 'completed_pages': run['completed_pages'], 'status': run['status'], 'page_map': relative}
