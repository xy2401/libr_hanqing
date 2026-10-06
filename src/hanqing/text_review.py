"""Checkpoint supplied human/assistant text-reading notes, without judging text."""

from datetime import datetime, timezone
import json
from pathlib import Path

from .ingest import digest, _save_manifest
from .models import validate_id
from .publication.xmlutil import project_path
from .transcription import _write_preserved


def record_text_review(root: Path, input_path: Path):
    root = root.resolve()
    input_path = project_path(root, input_path.resolve().relative_to(root).as_posix())
    supplied = json.loads(input_path.read_text(encoding='utf-8'))
    identity = validate_id(supplied['source_set_id'])
    review_id = validate_id(supplied['review_id'])
    task_id = validate_id(supplied['task_id'])
    directory = project_path(root, f'data/work/{identity}')
    if not input_path.is_relative_to(directory) or supplied.get('schema_version') != 1:
        raise ValueError('Keep the schema 1 review input in its source set')
    manifest_path = directory / 'manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    if manifest.get('schema_version') != 3 or manifest.get('path_base') != 'project':
        raise ValueError('Requires work manifest v3')
    task = next((t for t in manifest['recognition_tasks'] if t['task_id'] == task_id), None)
    if task is None or not supplied.get('policy') or supplied.get('method') != 'existing-markdown-context':
        raise ValueError('Supply a defined task, explicit policy and text-only review method')
    selected = {r['run_id'] for r in task['regions']}
    current = {p['physical_page']: p for r in manifest['recognition_runs'] if r['run_id'] in selected for p in r['pages']}
    numbers = set()
    if not isinstance(supplied.get('pages'), list) or not supplied['pages']:
        raise ValueError('Supply pages actually read')
    for page in supplied['pages']:
        number = page['physical_page']
        if number in numbers or number not in current:
            raise ValueError('Duplicate or out-of-task reviewed page')
        numbers.add(number)
        ref = current[number]
        if (page['markdown_path'] != ref['markdown_path'] or page['markdown_sha256'] != ref['markdown_sha256']
                or digest(project_path(root, page['markdown_path'])) != page['markdown_sha256']):
            raise ValueError('Reviewed current Markdown bytes differ')
        if (not isinstance(page.get('notes'), list) or any(not isinstance(s, str) for s in page['notes'])
                or not isinstance(page.get('findings'), list)):
            raise ValueError('Supply explicit reading notes and findings')
        for finding in page['findings']:
            if (not finding.get('id') or not finding.get('reason') or not finding.get('quote')
                    or finding['quote'] not in project_path(root, page['markdown_path']).read_text(encoding='utf-8')
                    or finding.get('status') not in {'pending-image-check', 'retained-from-text', 'corrected-from-text'}):
                raise ValueError('Finding requires a current text quote, reason and explicit status')
    reviews = manifest.setdefault('text_reviews', [])
    review = next((r for r in reviews if r['review_id'] == review_id), None)
    if review is None:
        review = {'review_id': review_id, 'task_id': task_id, 'method': supplied['method'], 'policy': supplied['policy'],
                  'started_at': datetime.now(timezone.utc).isoformat(), 'pages': [], 'input_records': [], 'status': 'partial-text-review'}
        reviews.append(review)
    elif any(review[k] != supplied[k] for k in ('task_id', 'method', 'policy')):
        raise ValueError('Review identity or policy changed')
    merged_pages = {p['physical_page']: p for p in review['pages']}
    merged_pages.update({p['physical_page']: p for p in supplied['pages']})
    findings = [f for p in merged_pages.values() for f in p['findings']]
    by_id = {f['id']: f for f in findings}
    if len(by_id) != len(findings):
        raise ValueError('Finding IDs must be unique throughout the review')
    resolutions = supplied.get('resolutions', [])
    if not isinstance(resolutions, list):
        raise ValueError('Resolutions must be an array')
    resolved_ids = set()
    for resolution in resolutions:
        finding_id = resolution.get('finding_id')
        if (finding_id in resolved_ids or finding_id not in by_id
                or by_id[finding_id]['status'] != 'pending-image-check'
                or resolution.get('status') != 'retained-from-text'
                or not resolution.get('reason') or not resolution.get('evidence')):
            raise ValueError('Resolution requires a pending finding and explicit text-based retention')
        resolved_ids.add(finding_id)
        for evidence in resolution['evidence']:
            page = current.get(evidence['physical_page'])
            if (page is None or evidence['markdown_path'] != page['markdown_path']
                    or evidence['markdown_sha256'] != page['markdown_sha256']
                    or digest(project_path(root, evidence['markdown_path'])) != evidence['markdown_sha256']
                    or not evidence.get('quote')
                    or evidence['quote'] not in project_path(root, evidence['markdown_path']).read_text(encoding='utf-8')):
                raise ValueError('Resolution evidence must quote current task Markdown bytes')
        previous = next((r for r in review.get('resolutions', []) if r['finding_id'] == finding_id), None)
        if previous and previous != resolution:
            raise ValueError('Previous resolution differs; use a new review ID')
    input_sha = digest(input_path)
    archive = project_path(root, f'data/cache/text-review-history/{input_sha}.json')
    archive.parent.mkdir(parents=True, exist_ok=True)
    if archive.exists() and archive.read_bytes() != input_path.read_bytes():
        raise ValueError('Review archive collision')
    if not archive.exists():
        archive.write_bytes(input_path.read_bytes())
    for page in supplied['pages']:
        previous = next((p for p in review['pages'] if p['physical_page'] == page['physical_page']), None)
        if previous and previous != page:
            raise ValueError('Previous reading checkpoint differs; use a new review ID')
        if not previous:
            review['pages'].append(page)
    for resolution in resolutions:
        if resolution not in review.setdefault('resolutions', []):
            review['resolutions'].append(resolution)
    review['pages'].sort(key=lambda p: p['physical_page'])
    ref = {'path': archive.relative_to(root).as_posix(), 'sha256': input_sha}
    if ref not in review['input_records']:
        review['input_records'].append(ref)
    completed = [p['physical_page'] for p in review['pages']]
    expected = list(range(task['scope']['first_physical_page'], task['scope']['last_physical_page'] + 1))
    # Changed pages invalidate earlier reading checkpoints; never claim a full current reading from old hashes.
    stale = [p['physical_page'] for p in review['pages'] if p['markdown_sha256'] != current[p['physical_page']]['markdown_sha256']
             or digest(project_path(root, p['markdown_path'])) != p['markdown_sha256']]
    stale_resolution_ids = [r['finding_id'] for r in review.get('resolutions', []) if any(
        e['markdown_sha256'] != current[e['physical_page']]['markdown_sha256']
        or digest(project_path(root, e['markdown_path'])) != e['markdown_sha256'] for e in r['evidence'])]
    review.update(completed_pages=completed, stale_pages=stale, last_saved_at=datetime.now(timezone.utc).isoformat())
    review['stale_resolution_ids'] = stale_resolution_ids
    review['status'] = 'text-reading-pass-complete-pending-image-check' if completed == expected and not stale and not stale_resolution_ids else 'partial-text-review'
    effective = {r['finding_id']: r['status'] for r in review.get('resolutions', []) if r['finding_id'] not in stale_resolution_ids}
    counts = {status: sum(effective.get(f['id'], f['status']) == status for f in by_id.values())
              for status in ('corrected-from-text', 'retained-from-text', 'pending-image-check')}
    review['finding_counts'] = counts
    lines = ['# 文字校勘记录', '', f'状态：{review["status"]}；已逐段阅读 {len(completed)}/{len(expected)} 个物理页的现有稿件。', '',
             supplied['policy'], '', '本轮依据现有 Markdown 文字；未看图复核，不证明初录无遗漏或全书影像校勘完成。', '',
             f'文字推校 {counts["corrected-from-text"]} 项；据文保留 {counts["retained-from-text"]} 项；待核 {counts["pending-image-check"]} 项。疑点项数不是确定错误数，也不替代初录疑点总表。', '',
             '## 逐页记录', '']
    for page in review['pages']:
        lines.extend([f'### 物理页 {page["physical_page"]}', '', f'输入 SHA-256：`{page["markdown_sha256"]}`。', ''])
        lines.extend('- ' + note for note in page['notes'])
        for finding in page['findings']:
            lines.append(f'- {finding["id"]} [{finding["status"]}]：{finding["quote"]} — {finding["reason"]}')
        lines.append('')
    if review.get('resolutions'):
        lines.extend(['## 后续文内说明', '', '原逐页判断保持历史字节；以下为据后文提出的保留决定，不表示原页字形已核。', ''])
        for resolution in review['resolutions']:
            status = 'stale-evidence' if resolution['finding_id'] in stale_resolution_ids else resolution['status']
            lines.append(f'- {resolution["finding_id"]} [{status}]：{resolution["reason"]}')
            for evidence in resolution['evidence']:
                lines.append(f'  - 物理页 {evidence["physical_page"]}：{evidence["quote"]}；SHA-256：`{evidence["markdown_sha256"]}`。')
        lines.append('')
    report = directory / f'editorial.{review_id}/text-review.md'
    sha = _write_preserved(root, report, '\n'.join(lines) + '\n')
    relative = report.relative_to(root).as_posix()
    entry = next((f for f in manifest['files'] if f['path'] == relative), None)
    if entry is None:
        manifest['files'].append({'path': relative, 'kind': 'text-review-report', 'sha256': sha, 'original_sha256': sha})
    else:
        entry['sha256'] = sha
    review.update(report_path=relative, report_sha256=sha, image_collation='not-performed', publication_acceptance='not-performed')
    _save_manifest(root, manifest_path, manifest)
    return {'review_id': review_id, 'reviewed_pages': len(completed), 'stale_pages': stale, 'status': review['status'], 'report_path': relative}
