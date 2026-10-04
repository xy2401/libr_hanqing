"""Deterministic EPUB candidates from src only; never marks a release."""

import hashlib
import json
from pathlib import Path
import platform
import subprocess
import tempfile
import zipfile

from ..validators.publication import check_source
from .. import __version__


def build_candidate(source_root: Path, output: Path) -> dict:
    source_root = source_root.resolve()
    output = output.resolve()
    if output.exists() or output.is_relative_to(source_root):
        raise ValueError("Candidate output must be new and outside src.")
    report = check_source(source_root)
    paths = sorted(p for p in source_root.rglob("*") if p.is_file() and p.name != ".gitkeep" and p.name != "mimetype")
    inputs = {path.relative_to(source_root).as_posix(): path.read_bytes() for path in [source_root / "mimetype", *paths]}
    source_files = {name: hashlib.sha256(content).hexdigest() for name, content in inputs.items()}
    source_digest = hashlib.sha256("".join(f"{name}\0{sha}\n" for name, sha in sorted(source_files.items())).encode("utf-8")).hexdigest()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=output.parent, suffix=".epub.tmp", delete=False) as stream:
            temporary = Path(stream.name)
        with zipfile.ZipFile(temporary, "w") as archive:
            for name, content in inputs.items():
                entry = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
                entry.compress_type = zipfile.ZIP_STORED if name == "mimetype" else zipfile.ZIP_DEFLATED
                entry.external_attr = 0o100644 << 16
                archive.writestr(entry, content)
        with zipfile.ZipFile(temporary) as archive:
            first = archive.infolist()[0]
            if first.filename != "mimetype" or first.compress_type != zipfile.ZIP_STORED or first.extra or archive.testzip():
                raise ValueError("Invalid OCF candidate archive.")
        temporary.rename(output)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
    return {"candidate_path": str(output), "sha256": hashlib.sha256(output.read_bytes()).hexdigest(), "bytes": output.stat().st_size, "source_sha256": source_digest, "source_files": source_files, "tools": {"hanqing": __version__, "python": platform.python_version()}, "structure": report, "release_status": "not-released"}


def run_epubcheck(candidate: Path, jar: Path, json_report: Path, java: str = "java") -> dict:
    if not jar.is_file():
        raise ValueError("EPUBCheck jar is missing.")
    if json_report.exists():
        raise FileExistsError(json_report)
    json_report.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run([java, "-jar", str(jar), str(candidate), "--json", str(json_report)], capture_output=True, encoding="utf-8", errors="replace", timeout=120)
    if not json_report.is_file():
        raise ValueError("EPUBCheck did not write its JSON report")
    checker = json.loads(json_report.read_text(encoding="utf-8"))["checker"]
    passed = result.returncode == 0 and checker["nError"] == 0 and checker["nFatal"] == 0
    return {"status": "passed" if passed else "failed", "exit_code": result.returncode, "stdout": result.stdout, "stderr": result.stderr, "report": str(json_report), "report_sha256": hashlib.sha256(json_report.read_bytes()).hexdigest(), "jar_sha256": hashlib.sha256(jar.read_bytes()).hexdigest(), "version": checker["checkerVersion"], "errors": checker["nError"], "fatals": checker["nFatal"], "warnings": checker["nWarning"]}
