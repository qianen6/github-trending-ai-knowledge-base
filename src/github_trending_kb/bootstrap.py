from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

from .domain import SCHEMA_VERSION
from .workspace import WorkspaceLayout


DIRECTORIES = (
    "daily",
    "evaluations",
    "incoming",
    "rejections",
    "repos",
    "readmes",
    "site/daily",
    "site/repos",
    "trending/html",
    "trending/raw",
    "trending/snapshots",
    "trending/evidence",
    "proof",
)


def initialize(root: Path) -> WorkspaceLayout:
    layout = WorkspaceLayout.initialize(root)
    for relative in DIRECTORIES:
        path = layout.path(relative)
        path.mkdir(parents=True, exist_ok=True)
    if not layout.catalog.exists():
        layout.catalog.write_text(
            json.dumps(
                {
                    "schema_version": SCHEMA_VERSION,
                    "updated_at": None,
                    "candidate_source": "GitHub Trending",
                    "dedupe_key": "full_name",
                    "entry_count": 0,
                    "entries": [],
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    if not layout.index.exists():
        layout.index.write_text(
            "# GitHub Trending 项目索引\n\n暂无正式收录。\n\n候选范围为 GitHub Trending，不代表 GitHub 全站排名。\n",
            encoding="utf-8",
        )
    return layout


def validate_codex_daily_task(root: Path) -> None:
    contract_path = root / ".codex" / "daily-task.json"
    setup_doc = root / "CODEX_SETUP.md"
    if not contract_path.is_file():
        raise ValueError("missing .codex/daily-task.json")
    if not setup_doc.is_file():
        raise ValueError("missing CODEX_SETUP.md")
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    expected = {
        "schema_version": 1,
        "contract": "codex-daily-task-installer",
        "kind": "cron",
        "status": "ACTIVE",
        "execution_environment": "local",
        "destination": "local",
        "project_root": ".",
        "prompt_file": "AUTOMATION_PROMPT.md",
        "prompt_format": "first-fenced-text-block",
    }
    for key, value in expected.items():
        if contract.get(key) != value:
            raise ValueError(f"invalid daily-task field {key}: {contract.get(key)!r}")
    if contract.get("schedule") != {
        "frequency": "daily",
        "time": "09:00",
        "timezone": "Asia/Shanghai",
    }:
        raise ValueError("invalid daily-task schedule")
    if not str(contract.get("name", "")).strip() or not str(
        contract.get("dedupe_key", "")
    ).strip():
        raise ValueError("daily-task name and dedupe_key are required")
    prompt_path = root / str(contract["prompt_file"])
    if not prompt_path.is_file():
        raise ValueError(f"missing automation prompt: {prompt_path.name}")
    prompt_doc = prompt_path.read_text(encoding="utf-8")
    match = re.search(r"```text\s*\n(.*?)\n```", prompt_doc, re.DOTALL)
    if not match or len(match.group(1).strip()) < 200:
        raise ValueError("AUTOMATION_PROMPT.md must contain a complete text code block")
    print(
        "CODEX DAILY TASK CONTRACT PASS "
        f"name={contract['name']} schedule=09:00 timezone=Asia/Shanghai "
        f"prompt_chars={len(match.group(1).strip())}"
    )


def run(command: list[str], root: Path) -> None:
    print("+ " + " ".join(command), flush=True)
    subprocess.run(command, cwd=root, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Initialize and verify a clean knowledge-base workspace"
    )
    parser.add_argument(
        "--root", type=Path, default=Path(__file__).resolve().parents[2]
    )
    parser.add_argument(
        "--check", action="store_true", help="build and run all validators/tests"
    )
    args = parser.parse_args()
    root = args.root.resolve()
    layout = initialize(root)
    validate_codex_daily_task(root)
    print(f"BOOTSTRAP PASS root={root} data_root={layout.data_root}")
    if args.check:
        run([sys.executable, "scripts/build_site.py", "--root", "."], root)
        run(
            [sys.executable, "scripts/trending_engine.py", "validate", "--root", "."],
            root,
        )
        run(
            [
                sys.executable,
                "scripts/readme_translations.py",
                "validate",
                "--root",
                ".",
            ],
            root,
        )
        run([sys.executable, "scripts/validate_site.py", "--root", "."], root)
        run(
            [
                sys.executable,
                "-m",
                "unittest",
                "discover",
                "-s",
                "tests",
                "-p",
                "test_*.py",
            ],
            root,
        )
        print("BOOTSTRAP CHECK PASS")
    return 0
