from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from github_trending_kb.transaction import ArtifactTransaction  # noqa: E402
from github_trending_kb.workspace import WorkspaceLayout  # noqa: E402
import github_trending_kb.transaction as transaction_module  # noqa: E402


class ArtifactTransactionTests(unittest.TestCase):
    def test_commit_writes_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            layout = WorkspaceLayout.discover(root)
            tx = ArtifactTransaction(layout, "2026-08-31")
            tx.stage_text("catalog.json", "new\n")
            manifest = tx.commit()
            self.assertEqual((root / "workspace/catalog.json").read_text(), "new\n")
            self.assertEqual(manifest["file_count"], 1)
            self.assertTrue((root / "workspace/.kb-state/commits/2026-08-31.json").is_file())

    def test_failure_restores_every_prior_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            layout = WorkspaceLayout.discover(root)
            layout.data_root.mkdir(parents=True)
            (layout.data_root / "a.txt").write_text("old-a", encoding="utf-8")
            (layout.data_root / "b.txt").write_text("old-b", encoding="utf-8")
            tx = ArtifactTransaction(layout, "2026-08-31")
            tx.stage_text("a.txt", "new-a")
            tx.stage_text("b.txt", "new-b")
            real_replace = transaction_module.os.replace
            calls = {"staged": 0}

            def fail_second_staged(source, target):
                if str(source).startswith(str(tx.staging)):
                    calls["staged"] += 1
                    if calls["staged"] == 2:
                        raise OSError("injected promotion failure")
                return real_replace(source, target)

            with patch.object(transaction_module.os, "replace", side_effect=fail_second_staged):
                with self.assertRaises(OSError):
                    tx.commit()
            self.assertEqual((layout.data_root / "a.txt").read_text(), "old-a")
            self.assertEqual((layout.data_root / "b.txt").read_text(), "old-b")
            self.assertFalse((layout.data_root / ".kb-state/transaction.json").exists())


if __name__ == "__main__":
    unittest.main()
