"""Stable bibliographic identifiers and metadata records."""

from __future__ import annotations

from dataclasses import dataclass
import re


class MetadataError(ValueError):
    """A book manifest contains invalid or inconsistent metadata."""


_ID_PATTERN = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*", re.ASCII)
_WINDOWS_RESERVED = {"con", "prn", "aux", "nul"} | {
    f"{prefix}{number}" for prefix in ("com", "lpt") for number in range(1, 10)
}
BOOK_STATUSES = frozenset({"draft", "recognized", "proofread", "ready", "released"})
CREATOR_ROLE_CODES = {
    "author": "aut", "editor": "edt", "annotator": "ann",
    "translator": "trl", "compiler": "com", "commentator": "cwt",
}
_LANGUAGE_PATTERN = re.compile(r"[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*", re.ASCII)


def validate_id(value: str) -> str:
    """Validate a portable, stable ID and return it without modification."""
    if not isinstance(value, str):
        raise MetadataError("ID must be a string")
    if not value or len(value) > 80 or _ID_PATTERN.fullmatch(value) is None:
        raise MetadataError(
            f"Invalid ID {value!r}: use at most 80 lowercase ASCII letters, "
            "digits, and single hyphens between segments"
        )
    if value in _WINDOWS_RESERVED:
        raise MetadataError(f"Invalid ID {value!r}: reserved Windows device name")
    return value


@dataclass(frozen=True, slots=True)
class Creator:
    id: str
    name: str
    role: str = "author"


@dataclass(frozen=True, slots=True)
class Series:
    id: str
    name: str
    position: int | None = None


@dataclass(frozen=True, slots=True)
class BookMetadata:
    """Publication metadata; scan provenance belongs to the local raw manifest."""

    schema_version: int
    id: str
    work_id: str
    title: str
    language: str
    edition: str
    status: str
    creators: tuple[Creator, ...] = ()
    series: tuple[Series, ...] = ()

    def __post_init__(self) -> None:
        validate_book(self)


def _check_string(value: object, context: str, *, allow_empty: bool = False) -> None:
    if not isinstance(value, str):
        raise MetadataError(f"{context}: must be a string")
    for character in value:
        codepoint = ord(character)
        if not (
            codepoint in {0x09, 0x0A, 0x0D}
            or 0x20 <= codepoint <= 0xD7FF
            or 0xE000 <= codepoint <= 0xFFFD
            or 0x10000 <= codepoint <= 0x10FFFF
        ):
            raise MetadataError(
                f"{context}: invalid XML 1.0 character U+{codepoint:04X}"
            )
    if not allow_empty and not value.strip():
        raise MetadataError(f"{context}: must not be empty")


def _check_id(value: object, context: str) -> None:
    try:
        validate_id(value)  # type: ignore[arg-type]
    except MetadataError as error:
        raise MetadataError(f"{context}: {error}") from error


def validate_book(book: BookMetadata) -> None:
    """Validate content invariants shared by direct construction and TOML loading."""
    if type(book.schema_version) is not int or book.schema_version != 1:
        raise MetadataError("book.schema_version: must be the integer 1")
    _check_id(book.id, "book.id")
    _check_id(book.work_id, "book.work_id")
    for field in ("title", "language", "edition", "status"):
        _check_string(getattr(book, field), f"book.{field}")
    if _LANGUAGE_PATTERN.fullmatch(book.language) is None:
        raise MetadataError(
            "book.language: must use basic language tag syntax, such as "
            "zh, zh-Hant, lzh-Hant, or en (no language registry lookup)"
        )
    if book.status not in BOOK_STATUSES:
        raise MetadataError(
            f"book.status: unsupported status {book.status!r}; expected "
            + ", ".join(sorted(BOOK_STATUSES))
        )
    for field, expected_type in (("creators", Creator), ("series", Series)):
        records = getattr(book, field)
        if not isinstance(records, tuple):
            raise MetadataError(f"book.{field}: must be a tuple of {expected_type.__name__} records")
        seen: set[str] = set()
        for index, record in enumerate(records):
            context = f"{field}[{index}]"
            if not isinstance(record, expected_type):
                raise MetadataError(f"{context}: must be a {expected_type.__name__} record")
            _check_id(record.id, f"{context}.id")
            if record.id in seen:
                raise MetadataError(f"{context}.id: duplicate ID {record.id!r}")
            seen.add(record.id)
            if isinstance(record, Creator):
                _check_string(record.name, f"{context}.name")
                _check_string(record.role, f"{context}.role")
                if record.role not in CREATOR_ROLE_CODES:
                    raise MetadataError(
                        f"{context}.role: unsupported creator role {record.role!r}; "
                        "expected " + ", ".join(sorted(CREATOR_ROLE_CODES))
                    )
            elif isinstance(record, Series):
                _check_string(record.name, f"{context}.name")
                if record.position is not None and (
                    type(record.position) is not int or record.position < 1
                ):
                    raise MetadataError(f"{context}.position: must be a positive integer")
