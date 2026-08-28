from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class EmptySiteTests(unittest.TestCase):
    def test_empty_repository_builds_and_validates(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            for name in ("daily", "repos", "site"):
                (root / name).mkdir(parents=True, exist_ok=True)
            (root / "index.md").write_text("# GitHub Trending 项目索引\n\n尚未执行首次采集。\n", encoding="utf-8")
            (root / "catalog.json").write_text(
                json.dumps(
                    {
                        "schema_version": 2,
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
            build = subprocess.run(
                [sys.executable, str(REPO_ROOT / "scripts" / "build_site.py"), "--root", str(root)],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(build.returncode, 0, build.stderr)
            self.assertIn("SITE PASS project_pages=0 daily_pages=0", build.stdout)
            home = (root / "site" / "index.html").read_text(encoding="utf-8")
            self.assertIn("暂无新增项目", home)

            validate = subprocess.run(
                [sys.executable, str(REPO_ROOT / "scripts" / "validate_site.py"), "--root", str(root)],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(validate.returncode, 0, validate.stderr)
            self.assertIn("markdown_projects=0 daily_reports=0 html_pages=1 broken_links=0", validate.stdout)


if __name__ == "__main__":
    unittest.main()
