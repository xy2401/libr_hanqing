"""Remove book copies of working records only after verifying retained work bytes."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from hanqing.publication.assemble import digest, read_context, save_manifest
from hanqing.publication.xmlutil import project_path


WORKING_FILES = ("notes.md", "review.toml", "text-review.md", "decisions.jsonl", "publication-validation.json")


def archive(root: Path, manifest: Path) -> dict:
    root, manifest = root.resolve(), manifest.resolve()
    if not manifest.is_relative_to(root / "data/work") or manifest.name != "manifest.json":
        raise ValueError("Use the source set's work manifest")
    data = json.loads(manifest.read_text(encoding="utf-8"))
    records = {f["path"]: f for f in data["files"]}
    removals, moves = [], []
    for relation in data["books"]:
        _, _, book = read_context(root, manifest, relation["book_id"])
        work = project_path(root, relation["editorial_directory"])
        if work.parent != manifest.parent or not work.name.startswith("editorial."):
            raise ValueError("Working records must be retained in this source set")
        for name in WORKING_FILES:
            source = project_path(root, f"{relation['book_directory']}/editorial/{name}")
            if not source.exists():
                continue
            target = project_path(root, f"{relation['editorial_directory']}/{name}")
            record = records[target.relative_to(root).as_posix()]
            if digest(target) != record["sha256"]:
                raise ValueError(f"Raw work changed since registration: {target}")
            sha = digest(source)
            retained = target
            if digest(retained) != sha:
                snapshots = [project_path(root, r["previous_snapshot"]) for r in record.get("revisions", [])]
                matches = [p for p in snapshots if p.is_relative_to(work) and digest(p) == sha]
                if not matches:
                    raise ValueError(f"Original book record bytes are not retained in work: {source}")
                retained = matches[0]
            old = source.relative_to(root).as_posix()
            moves.append({"from": old, "to": target.relative_to(root).as_posix(),
                          "original_sha256": sha, "retained_original": retained.relative_to(root).as_posix()})
            removals.append((source, retained, sha))
            former = record.pop("book_snapshot", {"path": old, "sha256": sha})
            record.setdefault("former_book_locations", []).append(former)
        summary = work / "publication-validation.json"
        if summary.is_file():
            relation.setdefault("publication_status", {})["validation_summary"] = {
                "path": summary.relative_to(root).as_posix(), "sha256": digest(summary)}

    # Preserve historical report bytes; update locations while retaining their old paths.
    for run in data.get("build_runs", []):
        summary = run.get("validation_summary", {})
        if not summary.get("path", "").startswith(f"books/{run['book_id']}/editorial/"):
            continue
        relation = next(b for b in data["books"] if b["book_id"] == run["book_id"])
        target = project_path(root, relation["editorial_directory"]) / "publication-validation.json"
        if digest(target) != summary["sha256"]:
            target = manifest.parent / f"validation.{run['book_id']}" / f"publication-validation.{summary['sha256']}.json"
        if digest(target) != summary["sha256"]:
            raise ValueError("Historical validation summary bytes are not retained")
        summary["previous_path"] = summary["path"]
        summary["path"] = target.relative_to(root).as_posix()
    if not removals:
        return {"removed_book_copies": 0}
    data.setdefault("relocations", []).append({"operation": "keep-working-editorial-only-in-work",
        "recorded_at": datetime.now(timezone.utc).isoformat(), "moves": moves,
        "accepted_records_and_publication_files_unchanged": True})
    save_manifest(manifest, data)
    # Each removal is a single, whitelisted file within its verified book directory.
    for source, retained, sha in removals:
        if digest(source) != sha or digest(retained) != sha:
            raise ValueError(f"Material changed before removing its duplicate: {source}")
        source.unlink()
    return {"removed_book_copies": len(removals), "retained_original_bytes": True}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--manifest", type=Path, required=True)
    arguments = parser.parse_args()
    print(json.dumps(archive(arguments.root, arguments.manifest), ensure_ascii=False))
