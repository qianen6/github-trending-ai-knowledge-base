from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import uuid
import re
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from .io_utils import atomic_bytes, atomic_json
from .workspace import WorkspaceLayout


@contextmanager
def workspace_lock(layout: WorkspaceLayout, name: str = "write.lock"):
    """OS-owned lock: process death releases it; another writer fails closed."""
    path = layout.state_root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        if path.stat().st_size == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise RuntimeError("workspace has an active publication writer") from exc
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _replace_tree_contents(source: Path, target: Path) -> None:
    """Replace files individually when Windows keeps the target directory open."""
    target.mkdir(parents=True, exist_ok=True)
    source_files = {
        path.relative_to(source) for path in source.rglob("*") if path.is_file()
    }
    target_files = {
        path.relative_to(target) for path in target.rglob("*") if path.is_file()
    }
    for relative in sorted(source_files, key=lambda path: path.as_posix()):
        source_file = source / relative
        target_file = target / relative
        target_file.parent.mkdir(parents=True, exist_ok=True)
        temp = target_file.with_name(f".{target_file.name}.{uuid.uuid4().hex}.tmp")
        shutil.copy2(source_file, temp)
        os.replace(temp, target_file)
    for relative in sorted(
        target_files - source_files, key=lambda path: path.as_posix(), reverse=True
    ):
        (target / relative).unlink(missing_ok=True)
    source_dirs = {
        path.relative_to(source) for path in source.rglob("*") if path.is_dir()
    }
    target_dirs = sorted(
        (path.relative_to(target) for path in target.rglob("*") if path.is_dir()),
        key=lambda path: (len(path.parts), path.as_posix()),
        reverse=True,
    )
    for relative in target_dirs:
        if relative not in source_dirs:
            (target / relative).rmdir()


def _replace_locked_directory(staged: Path, target: Path, backup: Path) -> None:
    """Use per-file atomic writes while retaining a restorable full-tree backup."""
    shutil.copytree(target, backup)
    try:
        _replace_tree_contents(staged, target)
    except Exception:
        _replace_tree_contents(backup, target)
        raise
    else:
        shutil.rmtree(staged)
        shutil.rmtree(backup)


def replace_directory_atomically(staged: Path, target: Path, backup_root: Path) -> None:
    """Swap a generated directory and restore the previous tree on failure."""
    backup = backup_root / f"{target.name}-{uuid.uuid4().hex[:12]}"
    backup.parent.mkdir(parents=True, exist_ok=True)
    had_target = target.exists()
    try:
        if had_target:
            os.replace(target, backup)
        os.replace(staged, target)
    except PermissionError:
        if had_target and target.exists() and not backup.exists():
            _replace_locked_directory(staged, target, backup)
            return
        if had_target and backup.exists() and not target.exists():
            os.replace(backup, target)
        raise
    except Exception:
        if had_target and backup.exists() and not target.exists():
            os.replace(backup, target)
        raise
    else:
        shutil.rmtree(backup, ignore_errors=True)


class ArtifactTransaction:
    """Stage a complete run and restore prior files if promotion fails."""

    def __init__(self, layout: WorkspaceLayout, run_id: str) -> None:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,100}", run_id):
            raise ValueError("invalid publication run id")
        self.layout = layout
        self.run_id = run_id
        self.transaction_id = f"{run_id}-{uuid.uuid4().hex[:12]}"
        self.staging = layout.state_root / "staging" / self.transaction_id
        self.backup = layout.state_root / "backups" / self.transaction_id
        self.journal = layout.state_root / "transaction.json"
        self._paths: set[Path] = set()
        self.staging.mkdir(parents=True, exist_ok=True)
        self.recover(layout)

    @staticmethod
    def recover(layout: WorkspaceLayout) -> bool:
        with workspace_lock(layout):
            return ArtifactTransaction._recover(layout)

    @staticmethod
    def _recover(layout: WorkspaceLayout) -> bool:
        journal = layout.state_root / "transaction.json"
        if not journal.is_file():
            return False
        data = json.loads(journal.read_text(encoding="utf-8"))
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,100}", data["run_id"]):
            raise ValueError("invalid recovery run id")
        backup = Path(data["backup"])
        if not backup.resolve().is_relative_to(
            (layout.state_root / "backups").resolve()
        ):
            raise ValueError("transaction backup is outside workspace backups")
        marker = layout.state_root / "commits" / f"{data['run_id']}.json"
        committed = (
            json.loads(marker.read_text(encoding="utf-8")) if marker.is_file() else {}
        )
        if committed.get("transaction_id") == data["transaction_id"]:
            expected_targets = {item["relative"] for item in data.get("targets", [])}
            if set(committed.get("files", {})) != expected_targets:
                raise ValueError("committed recovery manifest coverage mismatch")
            for relative, expected in committed.get("files", {}).items():
                target = layout.path(relative)
                if (
                    not target.is_file()
                    or hashlib.sha256(target.read_bytes()).hexdigest() != expected
                ):
                    raise ValueError(f"committed recovery hash mismatch: {relative}")
            journal.unlink()
            shutil.rmtree(backup, ignore_errors=True)
            shutil.rmtree(
                layout.state_root / "staging" / data["transaction_id"],
                ignore_errors=True,
            )
            return True
        for item in reversed(data.get("targets", [])):
            relative = Path(item["relative"])
            if relative.is_absolute() or ".." in relative.parts:
                raise ValueError("invalid transaction recovery target")
            target = layout.data_root / item["relative"]
            saved = backup / item["relative"]
            if item["existed"] and saved.is_file():
                target.parent.mkdir(parents=True, exist_ok=True)
                # Keep backups until recovery finishes, so recovery is re-entrant.
                atomic_bytes(target, saved.read_bytes())
            elif not item["existed"] and target.exists():
                target.unlink()
        journal.unlink(missing_ok=True)
        shutil.rmtree(backup, ignore_errors=True)
        return True

    def stage_text(self, relative: str | Path, text: str) -> None:
        rel = Path(relative)
        if rel.is_absolute() or ".." in rel.parts:
            raise ValueError(f"transaction path must be relative: {relative}")
        target = self.staging / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8", newline="\n")
        self._paths.add(rel)

    def stage_json(self, relative: str | Path, payload: Any) -> None:
        self.stage_text(
            relative, json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        )

    def track_tree(self) -> None:
        """Include files written directly by a publication implementation."""
        for path in self.staging.rglob("*"):
            if path.is_file():
                self._paths.add(path.relative_to(self.staging))

    def commit(self) -> dict[str, Any]:
        with workspace_lock(self.layout):
            self._recover(self.layout)
            return self._commit()

    def _commit(self) -> dict[str, Any]:
        targets = []
        for rel in sorted(self._paths, key=lambda p: p.as_posix()):
            target = self.layout.data_root / rel
            saved = self.backup / rel
            existed = target.is_file()
            if existed:
                saved.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(target, saved)
            targets.append({"relative": rel.as_posix(), "existed": existed})
        self.layout.state_root.mkdir(parents=True, exist_ok=True)
        atomic_json(
            self.journal,
            {
                "transaction_id": self.transaction_id,
                "run_id": self.run_id,
                "state": "committing",
                "backup": str(self.backup),
                "targets": targets,
            },
        )
        try:
            hashes: dict[str, str] = {}
            for item in targets:
                rel = Path(item["relative"])
                staged = self.staging / rel
                target = self.layout.data_root / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                with staged.open("r+b") as handle:
                    os.fsync(handle.fileno())
                os.replace(staged, target)
                hashes[rel.as_posix()] = hashlib.sha256(target.read_bytes()).hexdigest()
            manifest = {
                "schema_version": 1,
                "run_id": self.run_id,
                "transaction_id": self.transaction_id,
                "file_count": len(hashes),
                "files": hashes,
            }
            atomic_json(
                self.layout.state_root / "commits" / f"{self.run_id}.json", manifest
            )
            self.journal.unlink(missing_ok=True)
            shutil.rmtree(self.backup, ignore_errors=True)
            shutil.rmtree(self.staging, ignore_errors=True)
            return manifest
        except Exception:
            self._recover(self.layout)
            shutil.rmtree(self.staging, ignore_errors=True)
            raise
