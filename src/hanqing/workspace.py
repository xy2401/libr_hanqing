"""Migrate local working materials without changing accepted book content."""

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from .models import validate_id
from .publication.xmlutil import project_path


def _digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(chunk)
    return value.hexdigest()


def _artifact(root: Path, path: Path) -> dict:
    return {'path': path.relative_to(root).as_posix(), 'sha256': _digest(path), 'bytes': path.stat().st_size}


def _entries(directory: Path) -> list[Path]:
    """Do not silently omit an inaccessible directory from migration inventory."""
    result, pending = [], [directory]
    while pending:
        for path in sorted(pending.pop().iterdir()):
            result.append(path)
            if path.is_dir() and not path.is_symlink() and not getattr(path, 'is_junction', lambda: False)():
                pending.append(path)
    return sorted(result)


def _move_working_root(legacy: Path, working: Path) -> bool:
    """Fall back to individual file moves when Windows rejects directory moves."""
    try:
        legacy.rename(working)
        return False
    except PermissionError:
        # Do not merge with a destination another process may have created.
        working.mkdir()
    relocated = []
    try:
        entries = _entries(legacy)
        for directory in (p for p in entries if p.is_dir()):
            (working / directory.relative_to(legacy)).mkdir()
        for child in (p for p in entries if p.is_file()):
            destination = working / child.relative_to(legacy)
            child.rename(destination)
            relocated.append((child, destination))
    except OSError:
        for source, destination in reversed(relocated):
            destination.rename(source)
        for directory in sorted((p for p in _entries(working) if p.is_dir()), key=lambda p: len(p.parts), reverse=True):
            directory.rmdir()
        working.rmdir()
        raise
    return _remove_empty_legacy(legacy)


def _remove_empty_legacy(legacy: Path) -> bool:
    """Only remove verified empty directories, retaining locked empty shells."""
    entries = _entries(legacy)
    assert not any(p.is_file() or p.is_symlink() for p in entries)
    for directory in sorted([legacy, *(p for p in entries if p.is_dir())],
                            key=lambda p: len(p.parts), reverse=True):
        if any(directory.iterdir()):
            continue
        try:
            directory.rmdir()
        except PermissionError:
            pass
    return legacy.exists()


def migrate_data_layout(root: Path, check: bool = False) -> dict:
    """Preflight every destination, rename locally, verify all moved bytes.

    Old reports/plans remain byte-exact. Their embedded historical paths resolve
    through the recorded prefix migrations; current manifest pointers are updated.
    A cache journal and original manifests survive an interrupted migration.
    """
    root = root.resolve()
    legacy = project_path(root, 'data/raw')
    working = project_path(root, 'data/work')
    if not legacy.exists():
        if not check:
            for name in ('inbox', 'work', 'cache'):
                project_path(root, f'data/{name}').mkdir(parents=True, exist_ok=True)
        return {'status': 'already-current', 'working_directory': 'data/work'}
    if working.exists():
        completion = project_path(root, 'data/cache/layout-migration/layout-complete.json')
        if completion.is_file() and not any(p.is_file() or p.is_symlink() for p in _entries(legacy)):
            retained = True
            if not check:
                retained = _remove_empty_legacy(legacy)
            return {'status': 'already-current', 'working_directory': 'data/work',
                    'legacy_empty_directory_retained': retained}
        raise FileExistsError('data/work already exists; do not merge working directories automatically')
    entries = _entries(legacy)
    if any(p.is_symlink() or getattr(p, 'is_junction', lambda: False)() for p in entries):
        raise ValueError('Working migration may not follow symlinks or junctions')

    manifests = []
    routes = [('data/raw', 'data/work')]
    moves = []
    outputs = set()
    inventories = [_artifact(root, path) for path in entries if path.is_file()]
    for path in sorted(legacy.glob('*/manifest.json')):
        data = json.loads(path.read_text(encoding='utf-8'))
        if data.get('schema_version') != 3 or data.get('path_base') != 'project':
            raise ValueError('Migration requires schema 3 with project-relative paths')
        relations = data['books']
        if len({b['book_id'] for b in relations}) != len(relations):
            raise ValueError('Duplicate book relationships')
        for book in relations:
            identity = validate_id(book['book_id'])
            directory = project_path(root, book['book_directory'])
            if directory != root / 'books' / identity or not directory.is_dir():
                raise ValueError('Book directory must match its stable ID')
            distribution = project_path(root, f'books/{identity}/dist')
            for source in (path.parent / f'build.{identity}', path.parent / f'validation.{identity}'):
                if source.exists():
                    if not source.is_dir():
                        raise ValueError(f'Expected a packaging directory: {source}')
                    routes.append((source.relative_to(root).as_posix(), distribution.relative_to(root).as_posix()))
                    for file in _entries(source):
                        if file.is_file():
                            moves.append((file, distribution / file.relative_to(source)))
            editorial = project_path(root, book['editorial_directory'])
            summary = editorial / 'publication-validation.json'
            if summary.exists():
                routes.append((summary.relative_to(root).as_posix(), (distribution / summary.name).relative_to(root).as_posix()))
                moves.append((summary, distribution / summary.name))
            history = distribution / 'build-history.json'
            if history.exists() or history in outputs:
                raise FileExistsError(history)
            outputs.add(history)
        manifests.append((path, data))
    for source, destination in moves:
        # Both resolved paths must remain within the explicitly intended workspace.
        checked = project_path(root, destination.relative_to(root).as_posix())
        if checked != destination or not source.is_relative_to(legacy):
            raise ValueError('Migration path leaves its intended workspace')
        if destination.exists() or destination in outputs:
            raise FileExistsError(destination)
        outputs.add(destination)
    if not manifests:
        raise ValueError('No source-set manifests found; inspect loose legacy files before migrating')
    routes.sort(key=lambda pair: len(pair[0]), reverse=True)

    def relocate(value):
        if isinstance(value, str):
            for old, new in routes:
                if value == old or value.startswith(old + '/'):
                    return new + value[len(old):]
            return value
        if isinstance(value, list):
            return [relocate(item) for item in value]
        if isinstance(value, dict):
            return {relocate(key): (item if key in {'original_path', 'deduplicated_from', 'historical_path', 'from', 'previous_path'}
                                   else relocate(item)) for key, item in value.items()}
        return value

    result = {'status': 'checked-not-migrated' if check else 'migrated', 'source_sets': len(manifests),
              'working_files': len(inventories), 'packaging_files': len(moves),
              'bytes_verified': sum(row['bytes'] for row in inventories),
              'path_migrations': [{'from': old, 'to': new} for old, new in routes],
              'accepted_book_files_changed': False, 'epub_rebuilt': False}
    if check:
        return result
    recorded_at = datetime.now(timezone.utc).isoformat(timespec='seconds')
    journal = project_path(root, 'data/cache/layout-migration')
    journal.mkdir(parents=True, exist_ok=True)
    originals = {}
    for path, data in manifests:
        snapshot = journal / f"manifest.{_digest(path)}.json"
        if snapshot.exists() and snapshot.read_bytes() != path.read_bytes():
            raise FileExistsError(snapshot)
        snapshot.write_bytes(path.read_bytes())
        originals[path.relative_to(root).as_posix()] = _artifact(root, snapshot)
    inventory_path = journal / 'files-before.json'
    if inventory_path.exists():
        if json.loads(inventory_path.read_text(encoding='utf-8')) != inventories:
            raise ValueError('Interrupted migration source files changed; preserve and inspect the journal')
    else:
        inventory_path.write_text(json.dumps(inventories, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    working.parent.mkdir(parents=True, exist_ok=True)
    result['legacy_empty_directory_retained'] = _move_working_root(legacy, working)
    for source, destination in moves:
        # Keep the original relative path for history; physically it is now in work.
        current = working / source.relative_to(legacy)
        destination.parent.mkdir(parents=True, exist_ok=True)
        current.rename(destination)
    # Delete only the now-empty packaging directories, deepest first.
    for old, _ in routes:
        if '/build.' not in old and '/validation.' not in old:
            continue
        directory = working / Path(old).relative_to('data/raw')
        if directory.exists():
            assert directory.resolve().is_relative_to(working.resolve())
            for child in sorted((p for p in _entries(directory) if p.is_dir()), key=lambda p: len(p.parts), reverse=True):
                child.rmdir()
            directory.rmdir()
    for path, original in manifests:
        data = relocate(deepcopy(original))
        moved_path = root / relocate(path.relative_to(root).as_posix())
        runs = data.pop('build_runs', [])
        moved_records = []
        for book in data['books']:
            identity = book['book_id']
            prefix = f'books/{identity}/dist/'
            package_records = [row for row in data['files'] if row.get('path', '').startswith(prefix)]
            data['files'] = [row for row in data['files'] if not row.get('path', '').startswith(prefix)]
            status = book.get('publication_status', {})
            keys = ('candidate_path', 'candidate_sha256', 'source_sha256', 'epubcheck', 'reader_acceptance', 'release_status', 'validation_summary')
            candidate_state = {key: status.pop(key) for key in keys if key in status}
            history = root / prefix / 'build-history.json'
            history.parent.mkdir(parents=True, exist_ok=True)
            history.write_text(json.dumps({'book_id': identity, 'migration_recorded_at': recorded_at,
                'build_runs': [run for run in runs if run['book_id'] == identity],
                'candidate_status': candidate_state, 'artifacts': package_records,
                'artifact_bytes_preserved': True, 'epub_rebuilt': False}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
            moved_records.append(_artifact(root, history))
        migration = {**result, 'recorded_at': recorded_at, 'previous_manifest': originals[path.relative_to(root).as_posix()],
                     'historical_packaging_records': moved_records, 'historical_report_bytes_preserved': True}
        data.setdefault('data_layout_migrations', []).append(migration)
        data['files'].append({**originals[path.relative_to(root).as_posix()], 'kind': 'manifest-layout-snapshot'})
        temporary = moved_path.with_suffix('.json.tmp')
        if temporary.exists():
            raise FileExistsError(temporary)
        temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
        temporary.replace(moved_path)
    manifest_names = {path.relative_to(root).as_posix() for path, _ in manifests}
    for row in inventories:
        destination = root / relocate(row['path'])
        if row['path'] in manifest_names:
            assert _digest(root / originals[row['path']]['path']) == row['sha256']
        else:
            assert _digest(destination) == row['sha256'], destination
    for name in ('inbox', 'cache'):
        project_path(root, f'data/{name}').mkdir(parents=True, exist_ok=True)
    result['all_moved_bytes_verified'] = True
    receipt = {**result, 'recorded_at': recorded_at,
               'input_inventory': _artifact(root, inventory_path),
               'current_manifests': [_artifact(root, root / relocate(p.relative_to(root).as_posix()))
                                     for p, _ in manifests]}
    (journal / 'layout-complete.json').write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return result
