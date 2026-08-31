#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


DIRECTORIES = (
    "daily", "evaluations", "incoming", "rejections", "repos", "readmes",
    "site/daily", "site/repos", "trending/html", "trending/raw",
    "trending/snapshots", "trending/evidence", "proof",
)


def initialize(root: Path) -> None:
    for relative in DIRECTORIES:
        path = root / relative
        path.mkdir(parents=True, exist_ok=True)
        if relative not in {"trending/html", "trending/evidence", "proof"}:
            (path / ".gitkeep").touch(exist_ok=True)
    catalog = root / "catalog.json"
    if not catalog.exists():
        catalog.write_text(
            json.dumps(
                {
                    "schema_version": 4,
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
    index = root / "index.md"
    if not index.exists():
        index.write_text(
            "# GitHub Trending 项目索引\n\n暂无正式收录。\n\n候选范围为 GitHub Trending，不代表 GitHub 全站排名。\n",
            encoding="utf-8",
        )


def run(command: list[str], root: Path) -> None:
    print("+ " + " ".join(command), flush=True)
    subprocess.run(command, cwd=root, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Initialize and verify a clean knowledge-base workspace")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--check", action="store_true", help="build the empty site and run all validators/tests")
    args = parser.parse_args()
    root = args.root.resolve()
    initialize(root)
    print(f"BOOTSTRAP PASS root={root}")
    if args.check:
        run([sys.executable, "scripts/build_site.py", "--root", "."], root)
        run([sys.executable, "scripts/trending_engine.py", "validate", "--root", "."], root)
        run([sys.executable, "scripts/readme_translations.py", "validate", "--root", "."], root)
        run([sys.executable, "scripts/validate_site.py", "--root", "."], root)
        run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py"], root)
        print("BOOTSTRAP CHECK PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
