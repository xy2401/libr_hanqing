"""Persist candidate evidence without changing proofreading or release status."""

from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import tomllib
import xml.etree.ElementTree as ET

from .assemble import digest, tree_hashes
from .xmlutil import project_path


def _local_file(root: Path, value: str | Path) -> Path:
    path = Path(value)
    relative = path.relative_to(root).as_posix() if path.is_absolute() else path.as_posix()
    return project_path(root, relative)


def _check_mapping(root: Path, directory: Path) -> dict:
    mapping = directory / "editorial" / "source-map.jsonl"
    if not mapping.is_file() or not mapping.stat().st_size:
        return {"rows": 0, "anchors_and_baseline_hashes": "not-recorded"}
    ids, baselines = {}, {}
    rows = 0
    for line in mapping.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        xhtml = project_path(root, row["xhtml_path"])
        markdown = project_path(root, row["markdown_path"])
        if not xhtml.is_relative_to(directory / "src") or not markdown.is_relative_to(directory / "md"):
            raise ValueError("Paragraph mapping must reference this book's src/ and md/")
        if xhtml not in ids:
            ids[xhtml] = {node.get("id") for node in ET.parse(xhtml).iter() if node.get("id")}
        if row["element_id"] not in ids[xhtml]:
            raise ValueError(f"Stale paragraph mapping anchor: {row['element_id']}")
        if markdown not in baselines:
            baselines[markdown] = digest(markdown)
        if baselines[markdown] != row["markdown_sha256"]:
            raise ValueError(f"Stale paragraph mapping baseline: {markdown.name}")
        rows += 1
    return {"rows": rows, "anchors_and_baseline_hashes": "passed"}


def record_validation(root: Path, directory: Path, candidate: Path, result: dict) -> dict:
    """Verify actual bytes and save a build summary beside the candidate.

    ``result`` is produced by build_candidate + run_epubcheck. Reusing it requires
    unchanged candidate, report, publication source, baseline hashes and anchors.
    Reader evidence only survives when the candidate bytes remain identical.
    """
    root = root.resolve()
    directory = project_path(root, directory.relative_to(root).as_posix())
    if directory.parent != root / "books":
        raise ValueError("Use a books/<id>/ directory")
    editorial = project_path(root, directory.relative_to(root).as_posix() + "/editorial")
    distribution = project_path(root, directory.relative_to(root).as_posix() + "/dist")
    candidate = _local_file(root, candidate)
    checker_path = _local_file(root, result["epubcheck"]["report"])
    if candidate.parent != distribution or checker_path.parent != distribution:
        raise ValueError("Candidate and checker report belong in this book's dist/")
    if digest(candidate) != result["sha256"]:
        raise ValueError("Candidate SHA-256 changed since validation")
    if tree_hashes(directory / "src") != result["source_files"]:
        raise ValueError("Publication source changed since candidate construction")
    if digest(checker_path) != result["epubcheck"]["report_sha256"]:
        raise ValueError("EPUBCheck report SHA-256 changed")
    checker = json.loads(checker_path.read_text(encoding="utf-8"))["checker"]
    passed = result["epubcheck"]["exit_code"] == 0 and not checker["nFatal"] and not checker["nError"]
    review_path = editorial / "review.toml"
    review = tomllib.loads(review_path.read_text(encoding="utf-8")) if review_path.is_file() else {}
    conversion_path = editorial / "conversion-review.json"
    conversion = json.loads(conversion_path.read_text(encoding="utf-8")) if conversion_path.is_file() else {}
    destination = candidate.with_suffix(".validation.json")
    previous = json.loads(destination.read_text(encoding="utf-8")) if destination.is_file() else {}
    same_bytes = previous.get("candidate_sha256") == result["sha256"]
    summary = {
        "book_id": directory.name,
        "recorded_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": "candidate-validated" if passed else "candidate-check-failed",
        "candidate_sha256": result["sha256"], "candidate_bytes": candidate.stat().st_size,
        "candidate_path": candidate.relative_to(root).as_posix(),
        "source_version": "working-tree", "source_sha256": result["source_sha256"],
        "tools": {**result["tools"], "pandoc": conversion.get("pandoc", ""), "epubcheck": checker["checkerVersion"]},
        "structure": result["structure"],
        "epubcheck": {
            "status": "passed" if passed else "failed", "version": checker["checkerVersion"],
            "fatals": checker["nFatal"], "errors": checker["nError"], "warnings": checker["nWarning"],
            "jar_sha256": result["epubcheck"]["jar_sha256"],
            "report_sha256": result["epubcheck"]["report_sha256"],
            "report": checker_path.relative_to(root).as_posix(),
        },
        "markdown_mapping": _check_mapping(root, directory),
        "conversion_acceptance": "accepted-conversion-only" if conversion.get("status") == "conversion-accepted" else "not-recorded",
        "full_proofreading": review.get("status", "not-recorded"),
        "unresolved_items": review.get("unresolved_items"),
        "image_collation": review.get("text_review", {}).get("image_collation", "not-recorded"),
        "page_coverage": previous.get("page_coverage", "pending") if same_bytes else "pending",
        "reader_acceptance": previous.get("reader_acceptance", {"status": "pending"}) if same_bytes else {"status": "pending"},
        "release_status": "not-released",
    }
    if same_bytes and "checked_at" in previous:
        summary["checked_at"] = previous["checked_at"]
    archived = None
    if destination.exists():
        archived = checker_path.parent / f"publication-validation.{digest(destination)}.json"
        content = destination.read_bytes()
        if archived.exists():
            if archived.read_bytes() != content:
                raise ValueError("Validation summary archive hash collision")
        else:
            archived.write_bytes(content)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n", dir=distribution, suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
        temporary.replace(destination)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
    paths = {"path": destination.relative_to(root).as_posix(), "sha256": digest(destination)}
    if archived is not None:
        paths["previous_summary"] = archived.relative_to(root).as_posix()
    return paths
