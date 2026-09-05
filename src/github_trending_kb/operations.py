from __future__ import annotations
import argparse
import hashlib
import json
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from .engine import ingest, validate_root
from .incoming import validate_card_batch
from .io_utils import atomic_json, atomic_bytes
from .localization import validate_translations
from .site_builder import build_site
from .site_validation import validate_site
from .transaction import ArtifactTransaction, workspace_lock
from .workspace import WorkspaceLayout

DATA_PATHS = (
    "catalog.json",
    "index.md",
    "incoming",
    "evaluations",
    "rejections",
    "repos",
    "daily",
    "readmes",
    "site",
    "trending/raw",
    "trending/snapshots",
)


def fingerprint(root: Path, relatives: tuple[str, ...]) -> str:
    digest = hashlib.sha256()
    for relative in sorted(relatives):
        path = root / relative
        files = sorted(path.rglob("*")) if path.is_dir() else [path]
        for file in files:
            if file.is_file() and "__pycache__" not in file.parts:
                digest.update(file.relative_to(root).as_posix().encode("utf-8"))
                digest.update(hashlib.sha256(file.read_bytes()).digest())
    return digest.hexdigest()


class RunRecord:
    def __init__(self, root: Path, name: str, resume: bool = True):
        self.root = root
        self.path = WorkspaceLayout.discover(root).state_root / "runs" / f"{name}.json"
        try:
            self.data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.data = {"schema_version": 1, "stages": {}}
        self.resume = resume

    def step(self, name: str, key: str, action, output_key=None):
        old = self.data["stages"].get(name, {})
        if self.resume and old.get("status") == "passed" and old.get("input") == key:
            if output_key is None or old.get("output") == output_key():
                return {
                    "status": "reused",
                    "result": old["result"],
                    "elapsed_seconds": 0,
                }
        started = time.perf_counter()
        record = {
            "status": "running",
            "input": key,
            "started_at": datetime.now(timezone.utc).isoformat(),
        }
        self.data["stages"][name] = record
        atomic_json(self.path, self.data)
        try:
            result = action()
            record.update(
                status="passed",
                result=result,
                elapsed_seconds=round(time.perf_counter() - started, 3),
            )
            if output_key:
                record["output"] = output_key()
        except BaseException as exc:
            record.update(
                status="failed",
                error=f"{type(exc).__name__}: {exc}",
                elapsed_seconds=round(time.perf_counter() - started, 3),
            )
            atomic_json(self.path, self.data)
            raise
        atomic_json(self.path, self.data)
        return record


def verify_and_build(root: Path, resume: bool = True) -> dict:
    root = root.resolve()
    layout = WorkspaceLayout.discover(root)
    record = RunRecord(root, "verify", resume)
    code = fingerprint(Path(__file__).parents[2], ("src", "schemas", "pyproject.toml"))
    readme_inputs = ("workspace/readmes", "workspace/daily", "workspace/catalog.json")
    build_inputs = readme_inputs + (
        "workspace/repos",
        "workspace/evaluations",
        "workspace/incoming",
    )
    engine_inputs = (
        "README.md",
        "WORKFLOW.md",
        "SCREENING_RULES.md",
        "workspace/catalog.json",
        "workspace/index.md",
        "workspace/repos",
        "workspace/daily",
        "workspace/trending/snapshots",
        "workspace/.kb-state/commits",
    )
    for marker in (layout.state_root / "commits").glob("*.json"):
        manifest = json.loads(marker.read_text(encoding="utf-8"))
        engine_inputs += tuple(
            layout.path(name).relative_to(root).as_posix()
            for name in manifest.get("files", {})
        )
    results = {}
    with workspace_lock(layout, "run.lock"):
        for name, inputs, action, output in [
            ("readmes", readme_inputs, lambda: validate_translations(root), None),
            (
                "build",
                build_inputs,
                lambda: build_site(root),
                lambda: fingerprint(root, ("workspace/site",)),
            ),
            ("engine", engine_inputs, lambda: validate_root(root), None),
            (
                "site",
                build_inputs + ("workspace/site",),
                lambda: validate_site(root),
                None,
            ),
        ]:
            results[name] = record.step(
                name, code + fingerprint(root, inputs), action, output
            )
    return {
        "passed": len(results),
        "reused": sum(r["status"] == "reused" for r in results.values()),
        "stages": results,
    }


def prepare_batch(root: Path, input_path: Path) -> dict:
    root = root.resolve()
    layout = WorkspaceLayout.discover(root)
    payload = json.loads(input_path.read_text(encoding="utf-8-sig"))
    validate_card_batch(payload["repositories"])
    capture_date = payload["capture_date"]
    from datetime import date

    if date.fromisoformat(capture_date).isoformat() != capture_date:
        raise ValueError("invalid capture date")
    key = hashlib.sha256(input_path.read_bytes()).hexdigest()
    staging = layout.state_root / "publication-staging" / f"{capture_date}-{key[:12]}"
    record = RunRecord(root, f"publish-{capture_date}")
    current = fingerprint(
        root,
        tuple("workspace/" + p for p in DATA_PATHS if p not in ("readmes", "site")),
    )
    base_readmes = fingerprint(root, ("workspace/readmes",))
    code = fingerprint(Path(__file__).parents[2], ("src", "schemas", "pyproject.toml"))

    def prepare():
        if staging.exists():
            if not staging.resolve().is_relative_to(
                (layout.state_root / "publication-staging").resolve()
            ):
                raise ValueError("invalid staging path")
            shutil.rmtree(staging)
        staging.mkdir(parents=True)
        for name in ("README.md", "WORKFLOW.md", "SCREENING_RULES.md"):
            shutil.copy2(root / name, staging / name)
        if (root / "schemas").is_dir():
            shutil.copytree(root / "schemas", staging / "schemas")
        WorkspaceLayout.initialize(staging)
        for relative in DATA_PATHS:
            source = layout.path(relative)
            target = staging / "workspace" / relative
            if source.is_dir():
                shutil.copytree(source, target, dirs_exist_ok=True)
            elif source.is_file():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
        target_input = staging / "workspace/incoming" / f"{capture_date}.json"
        atomic_bytes(target_input, input_path.read_bytes())
        stats = ingest(staging, target_input)
        return {
            "staging_root": str(staging),
            "input_sha256": key,
            "capture_date": capture_date,
            "ingest": stats,
            "base_fingerprint": current,
            "base_readmes_fingerprint": base_readmes,
        }

    with workspace_lock(layout, "publish.lock"):
        # Stage content is deliberately editable for the evidence/translation step.
        result = record.step(
            "prepare",
            key + current + code,
            prepare,
            lambda: fingerprint(
                staging,
                (
                    "workspace/daily",
                    "workspace/evaluations",
                    "workspace/catalog.json",
                    "workspace/repos",
                    "workspace/incoming",
                ),
            ),
        )
    return result["result"]


def publish_batch(
    root: Path, input_path: Path, readmes_dir: Path | None = None
) -> dict:
    root = root.resolve()
    prepared = prepare_batch(root, input_path)
    layout = WorkspaceLayout.discover(root)
    stage = Path(prepared["staging_root"])
    with workspace_lock(layout, "publish.lock"):
        root_readmes = fingerprint(root, ("workspace/readmes",))
        if readmes_dir is None and root_readmes != prepared["base_readmes_fingerprint"]:
            raise ValueError(
                "live README changed since prepare; explicitly select --readmes-dir"
            )
        if readmes_dir:
            source = readmes_dir.resolve()
            if not source.is_relative_to(layout.data_root.resolve()):
                raise ValueError("localized README directory must be below workspace")
            target = stage / "workspace/readmes"
            if source != target.resolve() and (
                source.is_relative_to(target.resolve())
                or target.resolve().is_relative_to(source)
            ):
                raise ValueError("README source and destination overlap")
            if source != target.resolve() and target.exists():
                if not target.resolve().is_relative_to(stage.resolve()):
                    raise ValueError("invalid staged readmes")
                shutil.rmtree(target)
            if source != target.resolve():
                shutil.copytree(source, target)
        checks = verify_and_build(stage)
        tx = ArtifactTransaction(layout, prepared["capture_date"])
        for relative in DATA_PATHS:
            base = stage / "workspace" / relative
            for path in sorted(base.rglob("*")) if base.is_dir() else [base]:
                if path.is_file():
                    rel = path.relative_to(stage / "workspace")
                    dest = tx.staging / rel
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(path, dest)
        tx.track_tree()
        with workspace_lock(layout):
            current = fingerprint(
                root,
                tuple(
                    "workspace/" + p for p in DATA_PATHS if p not in ("readmes", "site")
                ),
            )
            if (
                current != prepared["base_fingerprint"]
                or fingerprint(root, ("workspace/readmes",)) != root_readmes
            ):
                raise ValueError(
                    "workspace changed during publication; prepare the batch again"
                )
            tx._recover(layout)
            manifest = tx._commit()
        record = RunRecord(root, f"publish-{prepared['capture_date']}")
        record.data["published"] = {
            "transaction_id": manifest["transaction_id"],
            "files": manifest["file_count"],
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }
        atomic_json(record.path, record.data)
        return {
            "committed_files": manifest["file_count"],
            "checked_stages": checks["passed"],
            "staging_root": str(stage),
        }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Resume deterministic checks and publish one validated file-backed generation"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("verify")
    run.add_argument("--root", type=Path, required=True)
    run.add_argument("--no-resume", action="store_true")
    for name in ("prepare", "publish"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--root", type=Path, required=True)
        cmd.add_argument("--input", type=Path, required=True)
        if name == "publish":
            cmd.add_argument("--readmes-dir", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "verify":
            result = verify_and_build(args.root, not args.no_resume)
        elif args.command == "prepare":
            result = prepare_batch(args.root, args.input)
        else:
            result = publish_batch(args.root, args.input, args.readmes_dir)
    except (OSError, ValueError, KeyError, RuntimeError, SystemExit) as exc:
        print(f"RUN FAIL {exc}")
        return 1
    print("RUN PASS " + json.dumps(result, ensure_ascii=False))
    return 0
