"""Intake PDFs and preserve their encoded page-image streams without OCR."""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
from uuid import uuid4

from . import __version__
from .models import validate_id
from .publication.xmlutil import project_path


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(chunk)
    return value.hexdigest()


def _pypdf():
    try:
        import pypdf
    except ImportError as error:
        raise ValueError('PDF intake needs pypdf in the chosen Python runtime; the pdf extra declares its version') from error
    if pypdf.__version__ not in {'6.10.0', '6.19.0'}:
        raise ValueError('Use the declared pypdf 6.19.0 or the existing bundled 6.10.0 runtime')
    return pypdf


def _plain(value, depth=0):
    from pypdf.generic import IndirectObject, NullObject, BooleanObject
    if isinstance(value, IndirectObject):
        return {'object_number': value.idnum, 'generation': value.generation}
    if isinstance(value, NullObject):
        return None
    if isinstance(value, BooleanObject):
        return value.value
    if depth > 16:
        return {'metadata_depth_limit': True}
    if isinstance(value, dict):
        return {str(k): _plain(v, depth + 1) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v, depth + 1) for v in value]
    if isinstance(value, bytes):
        return {'hex': value.hex()}
    if isinstance(value, (str, int, float)):
        return value
    return str(value)


def _read_pdf(path):
    reader = _pypdf().PdfReader(path, strict=True)
    if reader.is_encrypted:
        reader.close()
        raise ValueError('Encrypted PDFs are not supported by byte-exact stream extraction')
    return reader


def inspect_pdf(root: Path, source_path: str, source_set_id: str, expected_sha256=None) -> dict:
    root = root.resolve()
    source_set_id = validate_id(source_set_id)
    source = project_path(root, source_path)
    if source.parent != root / 'data/inbox' or source.suffix.lower() != '.pdf' or not source.is_file():
        raise ValueError('PDF intake accepts an existing file directly in data/inbox/')
    destination = project_path(root, f'data/work/{source_set_id}')
    if destination.exists():
        raise FileExistsError(f'Existing source set is preserved: {destination}')
    actual = digest(source)
    if expected_sha256 is not None and actual != expected_sha256:
        raise ValueError(f'Input SHA-256 changed: {source.name}')
    reader = _read_pdf(source)
    try:
        count = len(reader.pages)
        if not 0 < count <= 100_000:
            raise ValueError('PDF page count is outside supported limits')
        metadata = _plain(reader.metadata or {})
    finally:
        reader.close()
    return {'source_set_id': source_set_id, 'source_id': source_set_id + '-pdf',
            'inbox_path': source_path, 'original_name': source.name,
            'source_sha256': actual, 'source_bytes': source.stat().st_size,
            'page_count': count, 'pdf_metadata': metadata}


def _save_manifest(root, path, data):
    # A checkpoint never discards the prior manifest bytes.
    if path.exists():
        previous_sha = digest(path)
        archive = project_path(root, f'data/cache/manifest-history/{previous_sha}.json')
        archive.parent.mkdir(parents=True, exist_ok=True)
        original = path.read_bytes()
        if archive.exists() and archive.read_bytes() != original:
            raise ValueError('Manifest archive hash collision')
        if not archive.exists():
            archive.write_bytes(original)
        data.setdefault('manifest_history', []).append({
            'path': archive.relative_to(root).as_posix(), 'sha256': previous_sha})
    temporary = path.with_suffix('.json.tmp')
    if temporary.exists():
        # A write interrupted before replace is evidence, not disposable input.
        orphan = project_path(root, f'data/cache/manifest-history/interrupted-{digest(temporary)}.json')
        orphan.parent.mkdir(parents=True, exist_ok=True)
        if orphan.exists() and orphan.read_bytes() != temporary.read_bytes():
            raise ValueError('Interrupted manifest archive collision')
        if not orphan.exists():
            orphan.write_bytes(temporary.read_bytes())
        temporary.unlink()
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
    temporary.replace(path)


def _page_streams(reader, page):
    """Read encoded image bytes; never use page.images or PIL.Image.save."""
    from pypdf.generic import ContentStream, StreamObject
    images, seen, forms = [], set(), []

    def add(name, reference, role='image', depth=0):
        if depth > 32:
            raise ValueError('PDF resource nesting exceeds 32 levels')
        obj = reference.get_object()
        identity = (getattr(reference, 'idnum', None), getattr(reference, 'generation', None))
        if identity[0] is None:
            identity = ('direct', id(obj))
        if identity in seen:
            return
        seen.add(identity)
        if obj.get('/Subtype') == '/Form':
            forms.append({'name': name, 'object': _plain(reference),
                          'bbox': _plain(obj.get('/BBox')), 'matrix': _plain(obj.get('/Matrix'))})
            walk(obj.get('/Resources', {}), name, depth + 1)
        elif obj.get('/Subtype') == '/Image':
            raw = obj._data  # Version-pinned encoded bytes, before any filter decoding.
            if not isinstance(raw, bytes):
                raise ValueError('Image stream has no supported encoded byte representation')
            images.append((raw, {'resource_name': name, 'role': role,
                                'object': _plain(reference), 'dictionary': _plain(obj)}))
            for key, mask_role in (('/SMask', 'soft-mask'), ('/Mask', 'mask')):
                mask = obj.get(key)
                if mask is not None and isinstance(mask.get_object(), StreamObject):
                    add(name + key, mask, mask_role, depth + 1)

    def walk(resources, prefix='', depth=0):
        resources = resources.get_object() if hasattr(resources, 'get_object') else resources
        objects = resources.get('/XObject', {})
        objects = objects.get_object() if hasattr(objects, 'get_object') else objects
        for name, ref in objects.items():
            add(prefix + str(name), ref, depth=depth)

    walk(page.get('/Resources', {}))
    operations = ContentStream(page.get_contents(), reader).operations
    placements = []
    identity = [1, 0, 0, 1, 0, 0]
    current, stack = identity[:], []
    operator_names = []
    for operands, operator in operations:
        operator_names.append(operator.decode('latin-1'))
        if operator == b'q':
            stack.append(current[:])
        elif operator == b'Q':
            current = stack.pop() if stack else identity[:]
        elif operator == b'cm':
            a, b, c, d, e, f = [float(v) for v in operands]
            A, B, C, D, E, F = current
            current = [a*A+b*C, a*B+b*D, c*A+d*C, c*B+d*D, e*A+f*C+E, e*B+f*D+F]
        elif operator == b'Do':
            placements.append({'resource_name': str(operands[0]), 'matrix': current[:]})
        elif operator == b'INLINE IMAGE':
            images.append((operands['data'], {'resource_name': f'inline-{len(images)+1}',
                'role': 'inline-image', 'object': None, 'dictionary': _plain(operands['settings'])}))
    annotations = page.get('/Annots')
    crop = [float(v) for v in page.cropbox]
    full_page = False
    if len(images) == 1 and len(placements) == 1 and not forms and not annotations and set(operator_names) <= {'q','Q','cm','Do'}:
        matrix = placements[0]['matrix']
        full_page = (images[0][1]['resource_name'] == placements[0]['resource_name']
                     and int(page.get('/Rotate', 0)) == 0
                     and all(abs(a-b) < 0.02 for a,b in zip(matrix, [crop[2]-crop[0],0,0,crop[3]-crop[1],crop[0],crop[1]])))
    return images, {'media_box': [float(v) for v in page.mediabox], 'crop_box': crop,
                    'rotation': int(page.get('/Rotate', 0)), 'image_placements': placements,
                    'form_resources': forms, 'graphics_operators': sorted(set(operator_names)),
                    'has_annotations': bool(annotations), 'single_full_page_image': full_page}


def _suffix(raw, dictionary):
    filters = dictionary.get('/Filter', dictionary.get('/F', []))
    if not isinstance(filters, list):
        filters = [filters]
    if filters in (['/DCTDecode'], ['/DCT']) and raw.startswith(b'\xff\xd8'):
        return '.jpg'
    if filters in (['/JPXDecode'],) and raw.startswith((b'\x00\x00\x00\x0cjP  ', b'\xffO')):
        return '.jp2'
    return '.bin'


def _write_encoded(path, raw, *, completed=False):
    sha = hashlib.sha256(raw).hexdigest()
    if path.exists():
        if not path.is_file() or digest(path) != sha:
            raise ValueError(f'Existing image bytes differ: {path.name}')
    else:
        if completed:
            raise ValueError(f'Completed page stream is missing: {path.name}')
        with path.open('xb') as target:
            target.write(raw)
    if digest(path) != sha:
        raise ValueError(f'Written stream hash differs: {path.name}')
    return sha


def unpack_pdf(root: Path, manifest: Path, *, checkpoint_pages=25, max_output_bytes=2_147_483_648, progress=None) -> dict:
    if not 1 <= checkpoint_pages <= 1000 or max_output_bytes <= 0:
        raise ValueError('Use a positive output limit and checkpoint interval from 1 to 1000')
    root = root.resolve()
    manifest = project_path(root, manifest.relative_to(root).as_posix())
    if manifest.parent.parent != root / 'data/work' or manifest.name != 'manifest.json':
        raise ValueError('Use data/work/<source-set-id>/manifest.json')
    data = json.loads(manifest.read_text(encoding='utf-8'))
    if data.get('schema_version') != 3 or data.get('path_base') != 'project' or data.get('source_kind') != 'pdf':
        raise ValueError('PDF unpack requires a schema 3 PDF working manifest')
    source = project_path(root, data['source_path'])
    if source.parent != manifest.parent or source.name != 'original.pdf' or digest(source) != data['source_sha256']:
        raise ValueError('Original PDF path or SHA-256 changed')
    output = project_path(root, (manifest.parent / 'unpacked').relative_to(root).as_posix())
    output.mkdir(exist_ok=True)
    state = data.setdefault('pdf_unpack', {'method': 'encoded-image-streams', 'status': 'pending', 'pages': []})
    pages = {p['physical_page']: p for p in state['pages']}
    if len(pages) != len(state['pages']):
        raise ValueError('Duplicate physical page records')
    records = {row['path']: row for row in data['files']}
    reader = _read_pdf(source)
    run = {'run_id': 'pdf-unpack-' + uuid4().hex, 'started_at': datetime.now(timezone.utc).isoformat(),
           'source_id': data['source_id'], 'input_sha256': data['source_sha256'],
           'method': 'encoded-image-streams', 'recognition_method': None,
           'tools': {'hanqing': __version__, 'pypdf': _pypdf().__version__, 'python': platform.python_version()},
           'parameters': {'checkpoint_pages': checkpoint_pages, 'max_output_bytes': max_output_bytes,
                          'rendered': False, 'reencoded': False}, 'status': 'running'}
    data.setdefault('unpack_runs', []).append(run)
    state.update(status='running', page_count=len(reader.pages))
    data['pdf_metadata'] = _plain(reader.metadata or {})
    data['pdf_outline'] = _plain(reader.outline)
    _save_manifest(root, manifest, data)
    total_bytes, total_content_bytes = 0, 0
    try:
        for number, page in enumerate(reader.pages, 1):
            streams, info = _page_streams(reader, page)
            page_images = []
            for index, (raw, attributes) in enumerate(streams, 1):
                total_bytes += len(raw)
                if total_bytes + total_content_bytes > max_output_bytes:
                    raise ValueError('Encoded image output exceeds configured byte limit')
                name = f'page-{number:04d}' + (f'-image-{index:02d}' if len(streams) != 1 else '')
                path = project_path(root, (output / (name + _suffix(raw, attributes['dictionary']))).relative_to(root).as_posix())
                sha = _write_encoded(path, raw, completed=number in pages)
                relative = path.relative_to(root).as_posix()
                page_images.append({**attributes, 'path': relative, 'sha256': sha, 'bytes': len(raw)})
                records[relative] = {'path': relative, 'kind': 'pdf-image-stream', 'sha256': sha,
                    'original_sha256': sha, 'bytes': len(raw), 'source_id': data['source_id'],
                    'source_sha256': data['source_sha256'], 'physical_page': number,
                    'pdf_object': attributes['object'], 'encoded_bytes_preserved': True}
            complete = {'physical_page': number, 'original_page_number': None, 'status': 'saved-and-hash-verified',
                        **info, 'images': page_images}
            if not streams:
                from pypdf.generic import ArrayObject
                contents = page.raw_get('/Contents') if '/Contents' in page else []
                if hasattr(contents, 'get_object') and isinstance(contents.get_object(), ArrayObject):
                    contents = contents.get_object()
                references = list(contents) if isinstance(contents, (list, ArrayObject)) else [contents]
                content_rows = []
                for index, reference in enumerate(references, 1):
                    obj = reference.get_object()
                    raw = obj._data
                    total_content_bytes += len(raw)
                    if total_bytes + total_content_bytes > max_output_bytes:
                        raise ValueError('Encoded output exceeds configured byte limit')
                    path = project_path(root, (output/f'page-{number:04d}-content-{index:02d}.bin').relative_to(root).as_posix())
                    sha = _write_encoded(path, raw, completed=bool(pages.get(number, {}).get('content_streams')))
                    relative = path.relative_to(root).as_posix()
                    content_rows.append({'path': relative, 'sha256': sha, 'bytes': len(raw),
                                         'object': _plain(reference), 'dictionary': _plain(obj)})
                    records[relative] = {'path': relative, 'kind': 'pdf-content-stream', 'sha256': sha,
                        'original_sha256': sha, 'bytes': len(raw), 'source_id': data['source_id'],
                        'source_sha256': data['source_sha256'], 'physical_page': number,
                        'pdf_object': _plain(reference), 'encoded_bytes_preserved': True}
                complete.update(content_streams=content_rows, resources=_plain(page.get('/Resources', {})))
            if number in pages and pages[number] != complete:
                # Additive preservation of previously recorded non-image pages.
                old_shape = {k:v for k,v in complete.items() if k not in {'content_streams', 'resources'}}
                if pages[number] != old_shape:
                    raise ValueError(f'Existing page mapping differs: {number}')
            pages[number] = complete
            if number % checkpoint_pages == 0 or number == len(reader.pages):
                state['pages'] = [pages[n] for n in sorted(pages)]
                state['completed_pages'] = len(pages)
                data['files'] = list(records.values())
                _save_manifest(root, manifest, data)
                if progress:
                    progress({'source_set_id': data['source_set_id'], 'completed_pages': number, 'page_count': len(reader.pages)})
        # No page, image, and original hash is inferred from a success flag.
        if set(pages) != set(range(1, len(reader.pages)+1)) or digest(source) != data['source_sha256']:
            raise ValueError('Physical page coverage or original bytes changed')
        state.update(status='complete', completed_pages=len(pages), image_count=sum(len(p['images']) for p in pages.values()),
                     encoded_image_bytes=total_bytes, encoded_content_bytes=total_content_bytes, original_bytes_verified=True,
                     every_image_matches_encoded_pdf_stream=True,
                     single_full_page_image_pages=sum(p['single_full_page_image'] for p in pages.values()))
        run.update(status='complete', finished_at=datetime.now(timezone.utc).isoformat(), completed_pages=len(pages))
        _save_manifest(root, manifest, data)
        return {'source_set_id': data['source_set_id'], 'manifest': manifest.relative_to(root).as_posix(),
                'pages': len(pages), 'images': state['image_count'], 'output_bytes': total_bytes+total_content_bytes,
                'single_full_page_image_pages': state['single_full_page_image_pages'],
                'source_sha256': data['source_sha256'], 'status': 'unpacked-and-hash-verified'}
    except Exception as error:
        state['pages'] = [pages[n] for n in sorted(pages)]
        state.update(status='interrupted', completed_pages=len(pages), failed_page=number if 'number' in locals() else None)
        data['files'] = list(records.values())
        run.update(status='failed', error=str(error), finished_at=datetime.now(timezone.utc).isoformat())
        _save_manifest(root, manifest, data)
        raise
    finally:
        reader.close()


def intake_pdf(root: Path, row: dict, *, resume=False, progress=None) -> dict:
    root = root.resolve()
    identity = validate_id(row['source_set_id'])
    directory = project_path(root, f'data/work/{identity}')
    manifest = directory / 'manifest.json'
    if directory.exists():
        if not resume or not manifest.is_file():
            raise FileExistsError(f'Existing source set is preserved: {directory}')
        data = json.loads(manifest.read_text(encoding='utf-8'))
        if data['source_sha256'] != row['source_sha256'] or data['source_set_id'] != identity:
            raise ValueError('Resume requires the identical original source')
    else:
        checked = inspect_pdf(root, row['source_path'], identity, row['source_sha256'])
        if row.get('page_count', checked['page_count']) != checked['page_count']:
            raise ValueError('Planned PDF page count changed')
        source = project_path(root, checked['inbox_path'])
        directory.mkdir(parents=True)
        original = directory / 'original.pdf'
        try:
            source.rename(original)
        except OSError:
            directory.rmdir()
            raise
        if digest(original) != checked['source_sha256']:
            original.rename(source)
            directory.rmdir()
            raise ValueError('Source hash changed during intake')
        relative = original.relative_to(root).as_posix()
        data = {'schema_version': 3, 'path_base': 'project', 'source_set_id': identity,
                'source_id': checked['source_id'], 'source_kind': 'pdf', 'source_path': relative,
                'source_sha256': checked['source_sha256'], 'original_name': checked['original_name'],
                'intake': {'original_path': checked['inbox_path'], 'accepted_at': datetime.now(timezone.utc).isoformat(),
                           'input_and_original_bytes_verified': True},
                'pdf_metadata': checked['pdf_metadata'], 'books': [], 'book_relationships_status': 'not-defined',
                'files': [{'path': relative, 'kind': 'source-pdf', 'sha256': checked['source_sha256'],
                           'original_sha256': checked['source_sha256'], 'original_path': checked['inbox_path'],
                           'bytes': checked['source_bytes'], 'source_id': checked['source_id']}],
                'pdf_unpack': {'method': 'encoded-image-streams', 'status': 'pending', 'pages': [],
                              'expected_page_count': checked['page_count']}}
        _save_manifest(root, manifest, data)
    return unpack_pdf(root, manifest, progress=progress)


def intake_pdfs(root: Path, plan: Path, *, check=False, resume=False, progress=None) -> dict:
    root = root.resolve()
    plan = project_path(root, plan.relative_to(root).as_posix())
    data = json.loads(plan.read_text(encoding='utf-8'))
    rows = data.get('files', [])
    if data.get('schema_version') != 1 or not rows:
        raise ValueError('Use a schema 1 explicit PDF intake plan with files[]')
    if len({r['source_set_id'] for r in rows}) != len(rows) or len({r['source_path'] for r in rows}) != len(rows):
        raise ValueError('Duplicate source sets or PDF inputs in intake plan')
    checked = []
    for row in rows:
        identity = validate_id(row['source_set_id'])
        directory = project_path(root, f'data/work/{identity}')
        if directory.exists() and resume:
            manifest = directory / 'manifest.json'
            old = json.loads(manifest.read_text(encoding='utf-8'))
            if old['source_set_id'] != identity or digest(project_path(root, old['source_path'])) != row['source_sha256']:
                raise ValueError('Resume source identity/hash changed')
            checked.append({'source_set_id': identity, 'source_bytes': (directory/'original.pdf').stat().st_size,
                            'page_count': old['pdf_unpack']['expected_page_count']})
        else:
            item = inspect_pdf(root, row['source_path'], identity, row['source_sha256'])
            if row.get('page_count', item['page_count']) != item['page_count']:
                raise ValueError('Planned PDF page count changed')
            checked.append(item)
    if check:
        return {'status': 'checked-not-imported', 'pdf_count': len(checked),
                'source_bytes': sum(r['source_bytes'] for r in checked),
                'physical_pages': sum(r['page_count'] for r in checked), 'files': checked}
    results = [intake_pdf(root, row, resume=resume, progress=progress) for row in rows]
    return {'status': 'unpacked-and-hash-verified', 'pdf_count': len(results),
            'physical_pages': sum(r['pages'] for r in results), 'images': sum(r['images'] for r in results),
            'output_bytes': sum(r['output_bytes'] for r in results), 'source_sets': results}
