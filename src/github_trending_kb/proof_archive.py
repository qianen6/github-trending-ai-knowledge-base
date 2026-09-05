from __future__ import annotations
import argparse
import hashlib
import json
import re
import shutil
import tempfile
import zipfile
from datetime import date
from pathlib import Path
from .io_utils import atomic_json
from .workspace import WorkspaceLayout
from .transaction import workspace_lock


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def candidates(root: Path, before: date) -> list[Path]:
    proof = WorkspaceLayout.discover(root).path("proof").resolve()
    result = []
    for run in sorted(proof.glob("run-????-??-??")):
        if not re.fullmatch(r"run-\d{4}-\d{2}-\d{2}", run.name):
            continue
        if date.fromisoformat(run.name[4:]) >= before:
            continue
        target = (run / "rollback-test").resolve()
        if (
            target.is_dir()
            and target.is_relative_to(proof)
            and not (run / "rollback-test").is_symlink()
        ):
            result.append(target)
    return result


def verify_archive(archive: Path, manifest: dict) -> None:
    if file_hash(archive) != manifest["archive_sha256"]:
        raise ValueError("proof archive SHA-256 mismatch")
    with zipfile.ZipFile(archive) as bundle:
        if len(bundle.namelist()) != len(manifest["files"]) or set(
            bundle.namelist()
        ) != set(manifest["files"]):
            raise ValueError("proof archive file coverage mismatch")
        for name, expected in manifest["files"].items():
            rel = Path(name)
            if rel.is_absolute() or ".." in rel.parts or ":" in name or "\\" in name:
                raise ValueError("invalid archive member")
            digest = hashlib.sha256()
            with bundle.open(name) as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
            if digest.hexdigest() != expected["sha256"]:
                raise ValueError(f"proof archive member hash mismatch: {name}")


def active_references(layout: WorkspaceLayout, target: Path) -> list[str]:
    references = []

    def strings(value):
        if isinstance(value, str):
            yield value
        elif isinstance(value, dict):
            for key, item in value.items():
                yield str(key)
                yield from strings(item)
        elif isinstance(value, list):
            for item in value:
                yield from strings(item)

    for relative in (
        "catalog.json",
        "readmes/manifest.json",
        "incoming",
        "daily",
        "evaluations",
        "trending/snapshots",
        ".kb-state/commits",
    ):
        base = layout.path(relative)
        for path in base.rglob("*.json") if base.is_dir() else [base]:
            if path.is_file():
                value = json.loads(path.read_text(encoding="utf-8-sig"))
                references.extend(
                    (str(path), s.replace("\\", "/").casefold()) for s in strings(value)
                )
    absolute = target.as_posix().casefold()
    relative = target.relative_to(layout.data_root).as_posix().casefold()
    return sorted(
        {p for p, value in references if absolute in value or relative in value}
    )


def archive_proofs(root: Path, before: date, apply: bool = False) -> dict:
    layout = WorkspaceLayout.discover(root)
    with workspace_lock(layout):
        return _archive_proofs(root, before, apply)


def _archive_proofs(root: Path, before: date, apply: bool = False) -> dict:
    layout = WorkspaceLayout.discover(root)
    root_dir = layout.path("proof").resolve()
    report = []
    for target in candidates(root, before):
        hits = active_references(layout, target)
        if hits:
            raise ValueError(
                f"active manifests still reference proof target: {target} in {hits[:3]}"
            )
        paths = [p for p in sorted(target.rglob("*")) if p.is_file()]
        if any(
            p.is_symlink() or not p.resolve().is_relative_to(target)
            for p in target.rglob("*")
        ):
            raise ValueError(f"proof contains a link outside its snapshot: {target}")
        size = sum(p.stat().st_size for p in paths)
        item = {
            "target": str(target),
            "files": len(paths),
            "original_bytes": size,
            "status": "planned",
            "active_reference_count": 0,
        }
        if apply:
            archive = target.with_suffix(".zip")
            manifest_path = target.parent / "rollback-test.archive.json"
            if archive.exists():
                raise ValueError(
                    f"archive already exists; verify or restore it first: {archive}"
                )
            partial = archive.with_suffix(".zip.partial")
            records = {
                p.relative_to(target).as_posix(): {
                    "sha256": file_hash(p),
                    "bytes": p.stat().st_size,
                }
                for p in paths
            }
            try:
                with zipfile.ZipFile(
                    partial, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6
                ) as bundle:
                    for p in paths:
                        bundle.write(p, p.relative_to(target).as_posix())
                manifest = {
                    "schema_version": 1,
                    "target": str(target),
                    "files": records,
                    "archive_sha256": file_hash(partial),
                }
                verify_archive(partial, manifest)
                # Recheck live files before pruning; changed files abort the operation.
                current = {
                    p.relative_to(target).as_posix()
                    for p in target.rglob("*")
                    if p.is_file()
                }
                if current != set(records) or any(
                    file_hash(target / name) != row["sha256"]
                    for name, row in records.items()
                ):
                    raise ValueError("proof changed while archiving")
                partial.replace(archive)
                atomic_json(manifest_path, manifest)
                current = {
                    p.relative_to(target).as_posix()
                    for p in target.rglob("*")
                    if p.is_file()
                }
                if current != set(records) or any(
                    file_hash(target / name) != row["sha256"]
                    for name, row in records.items()
                ):
                    raise ValueError(
                        "proof changed after archive commit; source retained"
                    )
                if active_references(layout, target):
                    raise ValueError(
                        "active references changed during archive; source retained"
                    )
                resolved = target.resolve()
                if (
                    not resolved.is_relative_to(root_dir)
                    or resolved.name != "rollback-test"
                ):
                    raise ValueError("refusing unexpected proof target")
                # Remove only archived members; never recursively erase an unknown late file.
                for name, row in records.items():
                    path = resolved / name
                    if path.is_symlink() or not path.resolve().is_relative_to(resolved):
                        raise ValueError("proof path changed during pruning")
                    if file_hash(path) != row["sha256"]:
                        raise ValueError(
                            "proof changed during pruning; archive and remaining source retained"
                        )
                    path.unlink()
                for folder in sorted(
                    (p for p in resolved.rglob("*") if p.is_dir()),
                    key=lambda p: len(p.parts),
                    reverse=True,
                ):
                    folder.rmdir()
                resolved.rmdir()
                item.update(
                    status="archived",
                    archive=str(archive),
                    manifest=str(manifest_path),
                    archive_bytes=archive.stat().st_size,
                    saved_bytes=size - archive.stat().st_size,
                )
            finally:
                partial.unlink(missing_ok=True)
        report.append(item)
    return {
        "candidates": len(report),
        "applied": apply,
        "saved_bytes": sum(x.get("saved_bytes", 0) for x in report),
        "entries": report,
    }


def restore_archive(archive: Path, target: Path, workspace: Path) -> dict:
    archive = archive.resolve()
    target = target.resolve()
    workspace = workspace.resolve()
    if not target.is_relative_to(workspace) or target == workspace:
        raise ValueError("archive restoration must stay below workspace")
    if target.exists():
        raise ValueError("archive restoration target already exists")
    manifest = json.loads(
        (archive.parent / "rollback-test.archive.json").read_text(encoding="utf-8")
    )
    verify_archive(archive, manifest)
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=target.parent) as temp:
        stage = Path(temp) / "restored"
        stage.mkdir()
        with zipfile.ZipFile(archive) as bundle:
            for name in bundle.namelist():
                path = stage / name
                path.parent.mkdir(parents=True, exist_ok=True)
                with bundle.open(name) as source, path.open("wb") as output:
                    shutil.copyfileobj(source, output)
        for name, row in manifest["files"].items():
            if file_hash(stage / name) != row["sha256"]:
                raise ValueError("restored proof hash mismatch")
        stage.replace(target)
    return {"restored_files": len(manifest["files"]), "target": str(target)}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Archive old reproducible rollback-test copies; retain raw evidence and current runs"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    plan = sub.add_parser("archive")
    plan.add_argument("--root", type=Path, required=True)
    plan.add_argument("--before", type=date.fromisoformat, required=True)
    plan.add_argument("--apply", action="store_true")
    restore = sub.add_parser("restore")
    restore.add_argument("--root", type=Path, required=True)
    restore.add_argument("--archive", type=Path, required=True)
    restore.add_argument("--target", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "archive":
        result = archive_proofs(args.root, args.before, args.apply)
    else:
        result = restore_archive(
            args.archive, args.target, WorkspaceLayout.discover(args.root).data_root
        )
    print("PROOF PASS " + json.dumps(result, ensure_ascii=False))
    return 0
