from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from github_trending_kb.bootstrap import initialize  # noqa: E402
from github_trending_kb.workspace import WorkspaceLayout  # noqa: E402


class ArchitectureModuleTests(unittest.TestCase):
    def test_scripts_are_thin_cli_adapters_and_package_is_importable(self) -> None:
        for name in ("trending_engine.py", "build_site.py", "readme_translations.py", "validate_site.py", "bootstrap.py"):
            lines = (ROOT / "scripts" / name).read_text(encoding="utf-8").splitlines()
            self.assertLess(len(lines), 30, name)
        result = subprocess.run(
            [sys.executable, "-c", "import scripts.build_site; import scripts.trending_engine"],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_workspace_is_the_only_runtime_data_root(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            # Windows hosted runners may expose TEMP through an 8.3 alias.
            root = Path(temp).resolve()
            layout = initialize(root)
            self.assertEqual(layout.data_root, root / "workspace")
            self.assertTrue((root / "workspace/.kb-workspace").is_file())
            self.assertTrue((root / "workspace/catalog.json").is_file())
            self.assertEqual(WorkspaceLayout.discover(root).data_root, root / "workspace")
            self.assertFalse((root / "catalog.json").exists())


if __name__ == "__main__":
    unittest.main()
