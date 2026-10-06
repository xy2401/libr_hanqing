"""Apply explicit, hash-checked revisions only to work working Markdown."""
import argparse
from datetime import datetime, timezone
import difflib
import hashlib
import json
from pathlib import Path
import re
import sys

from hanqing.publication.assemble import digest, save_manifest
from hanqing.publication.xmlutil import project_path


def artifact(root, path):
    payload = path.read_bytes()
    return {"path": path.relative_to(root).as_posix(),
            "sha256": hashlib.sha256(payload).hexdigest(), "bytes": len(payload)}


def prepare(root, manifest, plan_path):
    root = root.resolve()
    manifest = manifest.resolve()
    plan_path = plan_path.resolve()
    if not manifest.is_relative_to(root / "data" / "work") or manifest.name != "manifest.json":
        raise ValueError("Use the unique work manifest")
    if not plan_path.is_relative_to(manifest.parent):
        raise ValueError("Keep the explicit revision plan in its source set")
    data = json.loads(manifest.read_text(encoding="utf-8"))
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    if data.get("schema_version") != 3 or plan.get("schema_version") != 1:
        raise ValueError("Unsupported schema")
    # Check metadata used during recording before any snapshot or manuscript is written.
    for field in ("revision_id", "scope", "prompt"):
        if not isinstance(plan.get(field), str) or not plan[field].strip():
            raise ValueError(f"Revision plan requires a non-empty {field}")
    if not isinstance(plan.get("operations"), list) or not plan["operations"]:
        raise ValueError("Revision plan requires operations")
    identifier = plan["revision_id"]
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,80}", identifier):
        raise ValueError("Invalid revision ID")
    if any(r["id"] == identifier for r in data.get("working_revisions", [])):
        raise ValueError("This revision is already recorded")
    method = plan.get("method", "assistant-native-multimodal")
    if method not in {"assistant-native-multimodal", "existing-markdown-context"}:
        raise ValueError("Unsupported revision method")
    index = {r["path"]: r for r in data["files"] if r.get("path")}
    prepared = []
    seen = set()
    for operation in plan["operations"]:
        if not isinstance(operation.get("reason"), str) or not operation["reason"].strip():
            raise ValueError("Every operation requires a non-empty reason")
        if (not isinstance(operation.get("finding_ids"), list) or not operation["finding_ids"]
                or not all(isinstance(value, str) and value.strip()
                           for value in operation["finding_ids"])):
            raise ValueError("Every operation requires finding_ids")
        path = project_path(root, operation["path"])
        if path in seen:
            raise ValueError("Group all edits to one manuscript in one operation")
        seen.add(path)
        relation = next(b for b in data["books"] if b["book_id"] == operation["book_id"])
        directory = project_path(root, relation["markdown_directory"])
        if not directory.is_relative_to(manifest.parent) or path.parent != directory:
            raise ValueError("Revisions may only edit this book's work working directory")
        if path.suffix != ".md" or path.name.endswith(".original.md"):
            raise ValueError("Do not revise an original snapshot")
        before = path.read_bytes()
        sha = hashlib.sha256(before).hexdigest()
        if sha != operation["expected_sha256"] or sha != index[operation["path"]]["sha256"]:
            raise ValueError(f"Stale input: {path}")
        evidence = []
        if method == "existing-markdown-context":
            if "replacement" in operation or operation.get("evidence_pages"):
                raise ValueError("Text revisions require explicit edits and text evidence only")
            allowed = {project_path(root, b["markdown_directory"]) for b in data["books"]}
            for value in operation.get("text_evidence", []):
                source = project_path(root, value["path"])
                if (not source.is_relative_to(manifest.parent) or source.parent not in allowed
                        or source.suffix != ".md" or source.name.endswith(".original.md")):
                    raise ValueError("Text evidence must refer to current work manuscripts")
                if (digest(source) != value["sha256"]
                        or digest(source) != index[value["path"]]["sha256"]):
                    raise ValueError(f"Changed text evidence: {source}")
                if not value.get("quote") or value["quote"] not in source.read_text(encoding="utf-8"):
                    raise ValueError("Text evidence quote is missing")
                evidence.append(value)
            ids = {value["id"] for value in evidence}
            if not evidence or len(ids) != len(evidence) or not all(ids):
                raise ValueError("Text revisions require distinct evidence IDs")
            for edit in operation["edits"]:
                if (not edit.get("reason") or not edit.get("evidence_ids")
                        or not set(edit["evidence_ids"]).issubset(ids)):
                    raise ValueError("Every text edit must explain and reference its evidence")
        else:
            if operation.get("text_evidence"):
                raise ValueError("Image revisions use source pages, not text-only evidence")
            for value in operation.get("evidence_pages", []):
                page = project_path(root, value["path"])
                if not page.is_relative_to(manifest.parent / "unpacked"):
                    raise ValueError("Evidence must refer to canonical unpacked pages")
                if digest(page) != value["sha256"] or digest(page) != index[value["path"]]["sha256"]:
                    raise ValueError(f"Changed source image: {page}")
                evidence.append(value)
            if not evidence:
                raise ValueError("Image revisions require source evidence")
        text = before.decode("utf-8")
        if "replacement" in operation:
            replacement = project_path(root, operation["replacement"]["path"])
            if not replacement.is_relative_to(root / "data"):
                raise ValueError("Keep replacement material in local data")
            if digest(replacement) != operation["replacement"]["sha256"]:
                raise ValueError("Replacement hash changed")
            after = replacement.read_bytes()
            after.decode("utf-8")
        else:
            for edit in operation["edits"]:
                if not edit["old"] or text.count(edit["old"]) != edit["occurrences"]:
                    raise ValueError(f"Unexpected replacement count: {path}, {edit['old']!r}")
                text = text.replace(edit["old"], edit["new"])
            after = text.encode("utf-8")
        if after == before:
            raise ValueError("No-op revision")
        snapshot = path.with_name(f"{path.stem}.{identifier}.original.md")
        if snapshot.exists() and snapshot.read_bytes() != before:
            raise FileExistsError(snapshot)
        diff_path = project_path(root, relation["editorial_directory"]) / f"{path.stem}.{identifier}.diff"
        if diff_path.exists():
            raise FileExistsError(diff_path)
        prepared.append((operation, relation, path, before, after, snapshot, diff_path, evidence))
    for relation in data["books"]:
        if relation["book_id"] not in {item[1]["book_id"] for item in prepared}:
            continue
        decisions = project_path(root, relation["editorial_directory"]) / "decisions.jsonl"
        previous = decisions.read_bytes() if decisions.exists() else b""
        key = decisions.relative_to(root).as_posix()
        if key in index and hashlib.sha256(previous).hexdigest() != index[key]["sha256"]:
            raise ValueError("Editorial decisions changed outside the manifest")
        snapshot = decisions.with_name(f"decisions.{identifier}.original.jsonl")
        if snapshot.exists() and snapshot.read_bytes() != previous:
            raise FileExistsError(snapshot)
    return data, plan, prepared


def apply(root, manifest, plan_path, check=False):
    root = root.resolve()
    data, plan, prepared = prepare(root, manifest, plan_path)
    if check:
        return {"status": "checked-not-applied", "manuscripts": len(prepared)}
    original_manifest = manifest.read_bytes()
    recorded_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    identifier = plan["revision_id"]
    method = plan.get("method", "assistant-native-multimodal")
    history = root / "data" / "cache" / "manifest-history" / data["source_set_id"] / f"manifest.{digest(manifest)}.json"
    history.parent.mkdir(parents=True, exist_ok=True)
    if history.exists() and history.read_bytes() != original_manifest:
        raise FileExistsError(history)
    history.write_bytes(original_manifest)
    records = []
    # Preserve every original before writing any working manuscript.
    for _, _, _, before, _, snapshot, _, _ in prepared:
        snapshot.write_bytes(before)
    input_snapshots = {operation["path"]: artifact(root, snapshot)
                       for operation, _, _, _, _, snapshot, _, _ in prepared}
    for operation, relation, path, before, after, snapshot, diff_path, evidence in prepared:
        path.write_bytes(after)
        difference = ''.join(difflib.unified_diff(before.decode('utf-8').splitlines(True),
                                                 after.decode('utf-8').splitlines(True),
                                                 fromfile=snapshot.relative_to(root).as_posix(),
                                                 tofile=path.relative_to(root).as_posix()))
        diff_path.write_text(difference, encoding="utf-8", newline="\n")
        record = {"id": f"{identifier}-{len(records)+1:02}",
                  "category": ("text-based-working-revision" if method == "existing-markdown-context"
                               else "image-based-working-revision"),
                  "manuscript": operation["path"], "book_id": relation["book_id"],
                  "before": artifact(root, snapshot), "after": artifact(root, path),
                  "diff": artifact(root, diff_path),
                  "reason": operation["reason"], "finding_ids": operation["finding_ids"],
                  "editor": "Codex", "edited_at": recorded_at,
                  "acceptance": "work-working-revision-only", "publication_applied": False}
        if method == "existing-markdown-context":
            record["text_evidence"] = [{**value, **({"input_snapshot": input_snapshots[value["path"]]}
                if value["path"] in input_snapshots else {})} for value in evidence]
        else:
            record["evidence_pages"] = evidence
        if "edits" in operation:
            record["edits"] = operation["edits"]
        if "transcription_scope" in operation:
            record["transcription_scope"] = operation["transcription_scope"]
        if "page_segments" in operation:
            record["page_segments"] = operation["page_segments"]
        if "replacement" in operation:
            material = operation["replacement"]
            if not any(row.get("path") == material["path"] for row in data["files"]):
                data["files"].append({**material, "kind":"working-revision-input", "revision_id":identifier})
        records.append(record)
        for row in data["files"]:
            if row.get("path") == operation["path"]:
                row.setdefault("revisions", []).append({"revision_id": identifier,
                    "previous_snapshot": record["before"]["path"],
                    "previous_sha256": record["before"]["sha256"],
                    "sha256": record["after"]["sha256"], "recorded_at": recorded_at})
                row.update(sha256=record["after"]["sha256"], bytes=record["after"]["bytes"])
        for value, kind in [(record["before"], "markdown-revision-snapshot"), (record["diff"], "working-revision-diff")]:
            if not any(r.get("path") == value["path"] for r in data["files"]):
                data["files"].append({**value, "kind": kind, "book_id": relation["book_id"],
                                      "work_id": relation["work_id"], "revision_id": identifier})
    affected = {record["book_id"] for record in records}
    for relation in data["books"]:
        if relation["book_id"] not in affected:
            continue
        decisions = project_path(root, relation["editorial_directory"]) / "decisions.jsonl"
        old_decisions = decisions.read_bytes() if decisions.exists() else b""
        decision_snapshot = decisions.with_name(f"decisions.{identifier}.original.jsonl")
        if decision_snapshot.exists() and decision_snapshot.read_bytes() != old_decisions:
            raise FileExistsError(decision_snapshot)
        decision_snapshot.write_bytes(old_decisions)
        data["files"].append({**artifact(root, decision_snapshot), "kind": "editorial-decision-snapshot",
                              "book_id": relation["book_id"], "work_id": relation["work_id"]})
        additions = ''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in records if r["book_id"] == relation["book_id"])
        decisions.write_bytes(old_decisions + (b'\n' if old_decisions and not old_decisions.endswith(b'\n') else b'') + additions.encode('utf-8'))
        known_decision = False
        for row in data["files"]:
            if row.get("path") == decisions.relative_to(root).as_posix():
                known_decision = True
                row.setdefault("revisions", []).append({"revision_id":identifier,
                    "previous_snapshot":decision_snapshot.relative_to(root).as_posix(),
                    "previous_sha256":digest(decision_snapshot),"sha256":digest(decisions)})
                row.update(artifact(root, decisions))
        if not known_decision:
            data["files"].append({**artifact(root, decisions), "kind":"editorial-decisions",
                                  "book_id":relation["book_id"], "work_id":relation["work_id"]})
        relation.setdefault("working_revision_ids", []).append(identifier)
        relation["publication_plan_working_input_status"] = "stale-after-working-revision"
        relation.setdefault("text_review", {})["current_input_status"] = "historical-after-working-revision"
        if "targeted_image_collation" in relation:
            relation["targeted_image_collation"]["current_input_status"] = "historical-after-working-revision"
        relation.setdefault("publication_status", {})["working_revision_pending_publication"] = identifier
    data["files"].append({**artifact(root, history), "kind": "manifest-snapshot", "revision_id": identifier})
    data["files"].append({**artifact(root, plan_path), "kind": "working-revision-plan", "revision_id": identifier})
    data.setdefault("working_revisions", []).append({"id": identifier, "recorded_at": recorded_at,
        "scope": plan["scope"], "status": "work-revised-pending-review", "schema_version": 1,
        "plan": artifact(root, plan_path), "previous_manifest": artifact(root, history),
        "records": records, "source_id": data["source_id"], "assistant": "Codex", "model": None,
        "method": method, "prompt": plan["prompt"],
        "processor":artifact(root, Path(__file__).resolve()),"python_version":sys.version.split()[0],
        "book_snapshots_updated": False, "accepted_xhtml_updated": False, "epub_rebuilt": False})
    if manifest.read_bytes() != original_manifest:
        raise ValueError("Manifest changed during revision")
    save_manifest(manifest, data)
    return {"status": "work-revised", "revision_id": identifier, "manuscripts": len(records)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    print(json.dumps(apply(Path.cwd(), args.manifest.resolve(), args.plan.resolve(), args.check), ensure_ascii=False))
