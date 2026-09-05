from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


WORKSPACE_MARKER = ".kb-workspace"


@dataclass(frozen=True)
class WorkspaceLayout:
    """Centralize all mutable runtime data below ``workspace/``."""

    project_root: Path
    data_root: Path

    @classmethod
    def discover(cls, root: Path) -> "WorkspaceLayout":
        project_root = root.resolve()
        workspace = project_root / "workspace"
        return cls(project_root=project_root, data_root=workspace)

    @classmethod
    def initialize(cls, root: Path) -> "WorkspaceLayout":
        project_root = root.resolve()
        workspace = project_root / "workspace"
        workspace.mkdir(parents=True, exist_ok=True)
        (workspace / WORKSPACE_MARKER).write_text(
            "GitHub Trending knowledge-base runtime workspace\n", encoding="utf-8"
        )
        return cls.discover(project_root)

    def path(self, relative: str | Path) -> Path:
        rel = Path(relative)
        if rel.is_absolute() or ".." in rel.parts:
            raise ValueError(f"workspace path must be relative: {relative}")
        path = self.data_root / rel
        if not path.resolve().is_relative_to(self.data_root.resolve()):
            raise ValueError(f"workspace path escapes data root: {relative}")
        return path

    @property
    def state_root(self) -> Path:
        return self.data_root / ".kb-state"

    @property
    def catalog(self) -> Path:
        return self.path("catalog.json")

    @property
    def index(self) -> Path:
        return self.path("index.md")

    @property
    def site(self) -> Path:
        return self.path("site")

    @property
    def daily(self) -> Path:
        return self.path("daily")

    @property
    def evaluations(self) -> Path:
        return self.path("evaluations")

    @property
    def incoming(self) -> Path:
        return self.path("incoming")

    @property
    def readmes(self) -> Path:
        return self.path("readmes")

    @property
    def repos(self) -> Path:
        return self.path("repos")

    @property
    def trending(self) -> Path:
        return self.path("trending")
