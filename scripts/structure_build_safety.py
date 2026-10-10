"""Standard-library-only guards to run before importing build/SDK modules.

Capture ``inventory_code(ROOT)`` before those imports and compare it again
before writing or freezing an artifact. The protected-path registry binds
physical files, not mutable SQLite metadata or a caller-selected baseline.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import stat
from typing import Iterable

REGISTRY_NAME = "structure_protected_paths.json"
REGISTRY_SCHEMA = "FINEATLAS_PROTECTED_PATHS_V1"
PROTECTED_ROLES = frozenset({"PRODUCTION", "SOURCE_CHECKPOINT", "ACCEPTED_SOURCE"})


def require_unoptimized() -> None:
    """Reject Python -O/-OO explicitly; safety checks must never disappear."""
    if not __debug__:
        raise RuntimeError("Optimized Python is forbidden for structural build and acceptance")


def _digest_file(path: Path) -> str:
    with path.open("rb") as stream:
        digest = hashlib.sha256()
        while block := stream.read(1024 * 1024):
            digest.update(block)
        return digest.hexdigest()


def inventory_code(root: Path | str) -> dict:
    """Return exactly the code/packaging fields of build_fingerprints.

    This module imports no FineAtlas SDK or builder. Generated caches and
    unrelated files are excluded by the existing .py/.json inventory contract.
    """
    root = Path(root).resolve(strict=True)
    if not root.is_dir():
        raise ValueError("Code root must be an existing directory")
    code = {}
    for directory in ("src/fineatlas", "scripts", "configs"):
        base = root / directory
        if not base.is_dir():
            raise ValueError("Required code inventory directory is missing: " + directory)
        for path in sorted(base.rglob("*")):
            if path.is_file() and path.suffix in {".py", ".json"}:
                code[str(path.relative_to(root))] = _digest_file(path)
    packaging = root / "pyproject.toml"
    if not packaging.is_file():
        raise ValueError("Required packaging file is missing: pyproject.toml")
    return {"code": code, "packaging": {"pyproject.toml": _digest_file(packaging)}}


def _existing_regular(path: Path | str, purpose: str) -> Path:
    try:
        resolved = Path(path).resolve(strict=True)
    except (OSError, RuntimeError) as error:
        raise ValueError(purpose + " must already exist") from error
    if not stat.S_ISREG(resolved.stat().st_mode):
        raise ValueError(purpose + " must be an existing regular file")
    return resolved


def _same_file(left: Path, right: Path) -> bool:
    return left == right or left.samefile(right)


def _file_stamp(path: Path) -> tuple:
    value = path.stat()
    return (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns)


def protect_output(database: Path | str, inputs: Path | str,
                   baseline: Path | str | None = None,
                   additional_protected: Iterable[Path | str] = ()) -> dict:
    """Validate a pre-copied output against authoritative protected inodes.

    Registry shape::

        {"schema": "FINEATLAS_PROTECTED_PATHS_V1", "files": [
            {"path": "/absolute/production.sqlite", "sha256": "...",
             "role": "PRODUCTION"}, ...]}

    Every registered file is protected, regardless of a caller's baseline
    argument. If supplied, baseline must be the actual registered production
    inode; equal hashes or copied metadata do not suffice. All operations are
    read-only. A candidate with identical bytes in an independent inode is
    permitted because the build starts from a complete production copy.
    """
    output_reference = Path(database)
    database = _existing_regular(output_reference, "Pre-copied output database")
    output_stamp = _file_stamp(database)
    registry_path = Path(inputs) / REGISTRY_NAME
    try:
        registry_bytes = registry_path.read_bytes()
        registry = json.loads(registry_bytes)
    except (OSError, ValueError) as error:
        raise ValueError("Frozen authoritative protected-path registry is required") from error
    if not isinstance(registry, dict) or registry.get("schema") != REGISTRY_SCHEMA:
        raise ValueError("Invalid authoritative protected-path registry schema")
    if _same_file(database, registry_path.resolve(strict=True)):
        raise ValueError("Refusing to modify the authoritative registry itself")
    files = registry.get("files")
    if not isinstance(files, list) or not files:
        raise ValueError("Protected-path registry must list protected files")
    validated = []
    for record in files:
        if not isinstance(record, dict) or record.get("role") not in PROTECTED_ROLES:
            raise ValueError("Every protected path needs an explicit supported role")
        raw_path, expected = record.get("path"), record.get("sha256")
        if not isinstance(raw_path, str) or not Path(raw_path).is_absolute():
            raise ValueError("Protected registry paths must be absolute")
        if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected):
            raise ValueError("Every protected path needs its frozen SHA-256")
        path = _existing_regular(raw_path, "Registered protected file")
        validated.append((path, record))
        if _same_file(database, path):
            raise ValueError("Refusing to modify registered " + record["role"] + ": " + raw_path)
    production = [path for path, record in validated if record["role"] == "PRODUCTION"]
    if not production:
        raise ValueError("Protected registry must identify the authoritative production file")
    if baseline is not None:
        baseline = _existing_regular(baseline, "Baseline")
        if not any(_same_file(baseline, path) for path in production):
            raise ValueError("Baseline must be the registered production inode; copies and metadata are insufficient")
    extra = [_existing_regular(path, "Additional protected file") for path in additional_protected]
    if any(_same_file(database, path) for path in extra):
        raise ValueError("Refusing to modify an additional protected file or its alias")
    # Recheck all source bytes before a caller can instantiate Migration. A
    # known role or a matching SQLite revision is not a content-integrity proof.
    checked_stamps = {}
    for path, record in validated:
        before = _file_stamp(path)
        if _digest_file(path) != record["sha256"]:
            raise ValueError("Registered protected file differs from its frozen SHA-256: " + str(path))
        after = _file_stamp(path)
        if before != after:
            raise ValueError("Protected file changed while its hash was checked")
        checked_stamps[path] = after
    # Catch path/inode replacement during long checks of large databases.
    current_output = _existing_regular(output_reference, "Pre-copied output database")
    if current_output != database or _file_stamp(current_output) != output_stamp:
        raise ValueError("Pre-copied output inode changed during source verification")
    for path, record in validated:
        if _file_stamp(path) != checked_stamps[path] or not _same_file(
                _existing_regular(record["path"], "Registered protected file"), path):
            raise ValueError("Protected inode changed during source verification")
    if registry_path.read_bytes() != registry_bytes:
        raise ValueError("Authoritative protected-path registry changed during verification")
    if any(_same_file(current_output, path) for path, _ in validated) or any(
            _same_file(current_output, path) for path in extra):
        raise ValueError("Output aliases a protected file after source verification")
    return {"database": str(current_output), "registry_sha256": hashlib.sha256(registry_bytes).hexdigest(),
            "protected_files": len(validated), "distinct_inode": True,
            "baseline_is_registered_production": baseline is not None}
