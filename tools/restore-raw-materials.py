"""Restore retained working materials from tracked book snapshots, without moving them."""

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil

from hanqing.models import validate_id
from hanqing.publication.assemble import digest, read_context, save_manifest
from hanqing.publication.xmlutil import project_path


def normalize_raw_records(root: Path, data: dict) -> int:
    """Adapt record links to the flat raw layout, retaining the previous bytes."""
    changed = 0
    now = datetime.now(timezone.utc).isoformat()
    for relation in data["books"]:
        directory = project_path(root, relation["editorial_directory"])
        work = relation["work_id"]
        validate_id(work)
        for record in list(data["files"]):
            path = project_path(root, record["path"])
            if path.parent != directory or path.suffix != ".md" or path.name.endswith(".original.md"):
                continue
            original = path.read_bytes()
            if digest(path) != record["sha256"]:
                raise ValueError(f"Recorded project material changed: {path}")
            text = original.decode("utf-8")
            updated = text.replace("../md/", f"../md.{work}/")
            updated = updated.replace(
                f"Markdown 文字底本保存在 `../md.{work}/` 并纳入 Git",
                f"Markdown 工作稿保存在 `../md.{work}/`；`books/{relation['book_id']}/md/` 保留 Git 快照")
            content = updated.encode("utf-8")
            if content == original:
                continue
            snapshot = path.with_name(path.stem + ".before-raw-layout.original.md")
            if snapshot.exists() and snapshot.read_bytes() != original:
                raise FileExistsError(snapshot)
            if not snapshot.exists():
                snapshot.write_bytes(original)
            snapshot_path = snapshot.relative_to(root).as_posix()
            data["files"].append({"path": snapshot_path, "sha256": digest(snapshot), "bytes": len(original),
                                  "kind": "project-record-snapshot", "book_id": relation["book_id"], "work_id": work})
            path.write_bytes(content)
            record.setdefault("revisions", []).append({"operation": "raw-record-link-layout", "edited_at": now,
                "previous_snapshot": snapshot_path, "previous_sha256": record["sha256"], "sha256": digest(path)})
            record.update(sha256=digest(path), bytes=len(content))
            changed += 1
    return changed


def restore(root: Path, manifest: Path) -> dict:
    root, manifest = root.resolve(), manifest.resolve()
    if not manifest.is_relative_to(root / "data" / "raw") or manifest.name != "manifest.json":
        raise ValueError("Use the source set's data/raw/<id>/manifest.json")
    data = json.loads(manifest.read_text(encoding="utf-8"))
    copies, replacements, previous_relations = [], {}, []
    for relation in data["books"]:
        _, _, book = read_context(root, manifest, relation["book_id"])
        work = relation["work_id"]
        validate_id(work)
        previous_relations.append(deepcopy(relation))
        for name, target_name in (("md", f"md.{work}"), ("editorial", f"editorial.{work}")):
            source = project_path(root, f"{relation['book_directory']}/{name}")
            target = project_path(root, (manifest.parent / target_name).relative_to(root).as_posix())
            if not source.is_dir():
                raise FileNotFoundError(source)
            if source.is_symlink() or any(p.is_symlink() for p in source.rglob("*")):
                raise ValueError(f"Material copies may not follow symlinks: {source}")
            for path in sorted(source.rglob("*")):
                if not path.is_file() or path.name == ".gitkeep":
                    continue
                destination = project_path(root, (target / path.relative_to(source)).relative_to(root).as_posix())
                sha = digest(path)
                if destination.exists() and (not destination.is_file() or digest(destination) != sha):
                    raise FileExistsError(f"Existing raw work is preserved: {destination}")
                old, new = path.relative_to(root).as_posix(), destination.relative_to(root).as_posix()
                replacements[old] = new
                copies.append({"source": old, "path": new, "sha256": sha, "bytes": path.stat().st_size,
                               "book_id": relation["book_id"], "work_id": work,
                               "kind": "markdown-material" if name == "md" else "project-record"})
        relation["markdown_directory"] = (manifest.parent / f"md.{work}").relative_to(root).as_posix()
        relation["markdown_snapshot_directory"] = f"{relation['book_directory']}/md"
        relation["editorial_directory"] = (manifest.parent / f"editorial.{work}").relative_to(root).as_posix()

    # Check every registered current input before making any copy or manifest change.
    current = {item["path"]: item for item in data["files"]}
    for item in copies:
        registered = current.get(item["source"])
        if registered and registered["sha256"] != item["sha256"]:
            raise ValueError(f"Registered material SHA-256 changed: {item['source']}")
    for item in copies:
        source, target = project_path(root, item["source"]), project_path(root, item["path"])
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            shutil.copy2(source, target)
        if digest(target) != item["sha256"]:
            raise ValueError(f"Retained copy SHA-256 mismatch: {target}")

    def remap(value):
        if isinstance(value, str):
            return replacements.get(value, value)
        if isinstance(value, list):
            return [remap(item) for item in value]
        if isinstance(value, dict):
            return {key: remap(item) for key, item in value.items()}
        return value

    now = datetime.now(timezone.utc).isoformat()
    raw_records = {item["path"]: item for item in data["files"]}
    for item in copies:
        old = raw_records.get(item["source"])
        if old and old.get("kind") == "ai-markdown":
            record = remap(deepcopy(old))
            data["files"][data["files"].index(old)] = record
        elif item["path"] in raw_records:
            record = raw_records[item["path"]]
        else:
            record = {key: item[key] for key in ("path", "sha256", "bytes", "book_id", "work_id", "kind")}
            data["files"].append(record)
        record["book_snapshot"] = {"path": item["source"], "sha256": item["sha256"], "recorded_at": now}
    for relation in data["books"]:
        for key in ("markdown_order", "page_map", "publication_plan", "publication_policy", "text_review"):
            if key in relation:
                relation[key] = remap(relation[key])
    adjusted = normalize_raw_records(root, data)
    data["material_policy"] = {"working_area": "raw", "book_markdown_role": "version-controlled-snapshot",
                               "promotion": "copy-after-explicit-item-acceptance", "retain_raw_after_promotion": True}
    data.setdefault("relocations", []).append({"operation": "restore-and-retain-raw-project-materials", "recorded_at": now,
        "method": "copy-with-sha256-verification", "copies": copies, "previous_book_relations": previous_relations,
        "historical_runs_unchanged": True, "accepted_publication_files_unchanged": True})
    save_manifest(manifest, data)
    return {"files": len(copies), "bytes": sum(item["bytes"] for item in copies), "working_area": "raw", "record_links_adjusted": adjusted}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--manifest", type=Path, required=True)
    arguments = parser.parse_args()
    print(json.dumps(restore(arguments.root, arguments.manifest), ensure_ascii=False))
