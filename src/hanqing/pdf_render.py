"""Prepare a registered full-page PDF raster for visual reading, without OCR."""

from datetime import datetime, timezone
import json
import math
from pathlib import Path

from . import __version__
from .ingest import digest, _save_manifest
from .models import validate_id
from .publication.xmlutil import project_path


def _pdfium():
    try:
        import pypdfium2
    except ImportError as error:
        raise ValueError('Page rendering needs an existing pypdfium2 runtime; no dependency is installed automatically') from error
    return pypdfium2


def render_pdf_page(root: Path, manifest_path: Path, physical_page: int, *, dpi=300):
    root = root.resolve()
    manifest_path = project_path(root, manifest_path.resolve().relative_to(root).as_posix())
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    identity = validate_id(manifest['source_set_id'])
    directory = project_path(root, f'data/work/{identity}')
    if (manifest_path != directory / 'manifest.json' or manifest.get('schema_version') != 3
            or manifest.get('path_base') != 'project' or manifest.get('source_kind') != 'pdf'):
        raise ValueError('Requires this source set work manifest v3 for a PDF')
    if type(physical_page) is not int or physical_page < 1 or type(dpi) is not int or not 72 <= dpi <= 600:
        raise ValueError('Supply a positive physical page and integer resolution from 72 to 600')
    source = project_path(root, manifest['source_path'])
    if source != directory / 'original.pdf' or digest(source) != manifest['source_sha256']:
        raise ValueError('Original PDF path or bytes changed')
    original_page = next((p for p in manifest['pdf_unpack']['pages'] if p['physical_page'] == physical_page), None)
    if original_page is None:
        raise ValueError('Physical page is absent from the unpacked page inventory')
    engine = _pdfium()
    parameters = {'dpi': dpi, 'scale': dpi / 72, 'additional_rotation': 0,
                  'additional_crop_lbrt': [0, 0, 0, 0], 'draw_annotations': True,
                  'form_fields': False, 'background_rgba': [255, 255, 255, 255]}
    output = project_path(root, f'data/work/{identity}/rendered/page-{physical_page:04d}-{dpi}dpi.png')
    relative = output.relative_to(root).as_posix()
    record = {'schema_version': 1, 'kind': 'pdf-full-page-render', 'physical_page': physical_page,
              'source_path': manifest['source_path'], 'source_sha256': manifest['source_sha256'],
              'path': relative, 'engine': 'pypdfium2', 'engine_version': str(engine.PYPDFIUM_INFO),
              'pdfium_version': str(engine.PDFIUM_INFO), 'parameters': parameters,
              'source_media_box': original_page.get('media_box'),
              'source_crop_box': original_page.get('crop_box'), 'source_rotation': original_page.get('rotation')}
    entries = manifest.setdefault('pdf_renderings', [])
    previous = next((r for r in entries if r['path'] == relative), None)
    if previous:
        if any(previous.get(k) != v for k, v in record.items()) or not output.is_file() or digest(output) != previous['sha256']:
            raise ValueError('Recorded rendering configuration or bytes changed; preserve it')
        return previous
    if output.exists():
        raise FileExistsError('Unregistered rendering is preserved; refusing to overwrite')
    with engine.PdfDocument(str(source)) as document:
        if physical_page > len(document):
            raise ValueError('Physical page exceeds the actual PDF page count')
        page = document[physical_page - 1]
        try:
            size = list(page.get_size())
            if any(not math.isfinite(v) or v <= 0 for v in size) or math.ceil(size[0] * dpi / 72) * math.ceil(size[1] * dpi / 72) > 30_000_000:
                raise ValueError('Rendered page exceeds the 30 million pixel limit')
            output.parent.mkdir(parents=True, exist_ok=True)
            bitmap = page.render(scale=dpi / 72, rotation=0, crop=(0, 0, 0, 0), draw_annots=True,
                                 may_draw_forms=False, fill_color=(255, 255, 255, 255))
            try:
                with bitmap.to_pil() as image:
                    dimensions = list(image.size)
                    # Only the newly rendered PNG is encoded; original image streams stay untouched.
                    with output.open('xb') as stream:
                        image.save(stream, format='PNG')
            finally:
                bitmap.close()
        finally:
            page.close()
    record.update(sha256=digest(output), page_view_size=size, dimensions=dimensions,
                  program_version=__version__, created_at=datetime.now(timezone.utc).isoformat())
    entries.append(record)
    manifest['files'].append({'path': relative, 'kind': record['kind'], 'sha256': record['sha256'],
                              'source_id': manifest['source_id'], 'physical_page': physical_page,
                              'source_sha256': manifest['source_sha256']})
    _save_manifest(root, manifest_path, manifest)
    return record
