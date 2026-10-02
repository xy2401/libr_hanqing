"""Read and validate the version-controlled book catalog."""

from __future__ import annotations

from pathlib import Path
import tomllib
from typing import Any

from .models import BookMetadata, Creator, MetadataError, Series, Source, validate_id


_BOOK_FIELDS = {
    "schema_version", "id", "work_id", "title", "language", "edition", "status",
    "primary_source_id", "creators", "series", "sources",
}


def _check_fields(data: dict[str, Any], allowed: set[str], context: str) -> None:
    unknown = sorted(set(data) - allowed)
    if unknown:
        raise MetadataError(f"{context}: unknown field(s): {', '.join(unknown)}")


def _string(
    data: dict[str, Any], key: str, context: str, *, default: str | None = None,
    allow_empty: bool = False,
) -> str:
    if key not in data:
        if default is None:
            raise MetadataError(f"{context}.{key}: required field is missing")
        value = default
    else:
        value = data[key]
    if not isinstance(value, str):
        raise MetadataError(f"{context}.{key}: must be a string")
    if not allow_empty and not value.strip():
        raise MetadataError(f"{context}.{key}: must not be empty")
    return value


def _identifier(data: dict[str, Any], key: str, context: str) -> str:
    value = _string(data, key, context)
    try:
        return validate_id(value)
    except MetadataError as error:
        raise MetadataError(f"{context}.{key}: {error}") from error


def _records(data: dict[str, Any], key: str) -> list[dict[str, Any]]:
    value = data.get(key, [])
    if not isinstance(value, list):
        raise MetadataError(f"{key}: must be an array of tables")
    for index, record in enumerate(value):
        if not isinstance(record, dict):
            raise MetadataError(f"{key}[{index}]: must be a table")
    return value


def _parse_book(data: dict[str, Any]) -> BookMetadata:
    _check_fields(data, _BOOK_FIELDS, "book")
    schema_version = data.get("schema_version")
    if type(schema_version) is not int or schema_version != 1:
        raise MetadataError("book.schema_version: must be the integer 1")
    book_id = _identifier(data, "id", "book")
    work_id = _identifier(data, "work_id", "book")
    title = _string(data, "title", "book")
    language = _string(data, "language", "book")
    edition = _string(data, "edition", "book")
    status = _string(data, "status", "book")
    primary_source_id = _string(
        data, "primary_source_id", "book", default="", allow_empty=True,
    )
    creators: list[Creator] = []
    for index, record in enumerate(_records(data, "creators")):
        context = f"creators[{index}]"
        _check_fields(record, {"id", "name", "role"}, context)
        identifier = _identifier(record, "id", context)
        creators.append(Creator(
            id=identifier,
            name=_string(record, "name", context),
            role=_string(record, "role", context, default="author"),
        ))

    series: list[Series] = []
    for index, record in enumerate(_records(data, "series")):
        context = f"series[{index}]"
        _check_fields(record, {"id", "name", "position"}, context)
        identifier = _identifier(record, "id", context)
        position = record.get("position")
        series.append(Series(
            id=identifier,
            name=_string(record, "name", context),
            position=position,
        ))

    sources: list[Source] = []
    for index, record in enumerate(_records(data, "sources")):
        context = f"sources[{index}]"
        _check_fields(
            record, {"id", "kind", "path", "sha256", "url", "description"}, context,
        )
        identifier = _identifier(record, "id", context)
        kind = _string(record, "kind", context)
        path = _string(record, "path", context)
        sha256 = _string(record, "sha256", context, default="", allow_empty=True)
        sources.append(Source(
            id=identifier, kind=kind, path=path, sha256=sha256.lower(),
            url=_string(record, "url", context, default="", allow_empty=True),
            description=_string(record, "description", context, default="", allow_empty=True),
        ))

    return BookMetadata(
        schema_version=schema_version, id=book_id, work_id=work_id, title=title,
        language=language, edition=edition, status=status,
        primary_source_id=primary_source_id, creators=tuple(creators),
        series=tuple(series), sources=tuple(sources),
    )


def load_book(path: Path) -> BookMetadata:
    """Load one UTF-8 ``books/<id>/book.toml`` manifest.

    Asset existence is deliberately independent of catalog validity: ignored
    local scans need not be present in every checkout.
    """
    path = Path(path)
    try:
        with path.open("rb") as stream:
            data = tomllib.load(stream)
        book = _parse_book(data)
        if path.name != "book.toml" or path.parent.parent.name != "books":
            raise MetadataError("manifest must be located at books/<id>/book.toml")
        if path.parent.name != book.id:
            raise MetadataError(
                f"book.id: {book.id!r} does not match directory {path.parent.name!r}"
            )
        return book
    except (OSError, UnicodeError, tomllib.TOMLDecodeError, MetadataError) as error:
        raise MetadataError(f"{path}: {error}") from error


def discover_books(root: Path) -> list[BookMetadata]:
    """Return all manifests beneath a project root, ordered by stable book ID."""
    books = Path(root) / "books"
    if not books.exists():
        return []
    if not books.is_dir():
        raise MetadataError(f"{books}: catalog path must be a directory")
    result: list[BookMetadata] = []
    for directory in sorted(books.iterdir()):
        if directory.name.startswith(".") or not directory.is_dir():
            continue
        manifest = directory / "book.toml"
        if not manifest.is_file():
            raise MetadataError(f"{manifest}: book directory is missing book.toml")
        result.append(load_book(manifest))
    return result
