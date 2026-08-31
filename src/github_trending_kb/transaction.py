from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Any

from .io_utils import atomic_json
from .workspace import WorkspaceLayout


def replace_directory_atomically(staged: Path, target: Path, backup_root: Path) -> None:
    """Swap a generated directory and restore the previous tree on failure."""
    backup = backup_root / f"{target.name}-{uuid.uuid4().hex[:12]}"
    backup.parent.mkdir(parents=True, exist_ok=True)
    had_target = target.exists()
    try:
        if had_target:
            os.replace(target, backup)
        os.replace(staged, target)
    except Exception:
        if had_target and backup.exists() and not target.exists():
            os.replace(backup, target)
        raise
    else:
        shutil.rmtree(backup, ignore_errors=True)


class ArtifactTransaction:
    """Stage a complete run and restore prior files if promotion fails."""

    def __init__(self, layout: WorkspaceLayout, run_id: str) -> None:
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
        journal = layout.state_root / "transaction.json"
        if not journal.is_file():
            return False
        data = json.loads(journal.read_text(encoding="utf-8"))
        backup = Path(data["backup"])
        for item in reversed(data.get("targets", [])):
            target = layout.data_root / item["relative"]
            saved = backup / item["relative"]
            if item["existed"] and saved.is_file():
                target.parent.mkdir(parents=True, exist_ok=True)
                os.replace(saved, target)
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
        self.stage_text(relative, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")

    def track_tree(self) -> None:
        """Include files written directly by a publication implementation."""
        for path in self.staging.rglob("*"):
            if path.is_file():
                self._paths.add(path.relative_to(self.staging))

    def commit(self) -> dict[str, Any]:
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
                os.replace(staged, target)
                hashes[rel.as_posix()] = hashlib.sha256(target.read_bytes()).hexdigest()
            manifest = {
                "schema_version": 1,
                "run_id": self.run_id,
                "transaction_id": self.transaction_id,
                "file_count": len(hashes),
                "files": hashes,
            }
            atomic_json(self.layout.state_root / "commits" / f"{self.run_id}.json", manifest)
            self.journal.unlink(missing_ok=True)
            shutil.rmtree(self.backup, ignore_errors=True)
            shutil.rmtree(self.staging, ignore_errors=True)
            return manifest
        except Exception:
            self.recover(self.layout)
            shutil.rmtree(self.staging, ignore_errors=True)
            raise
