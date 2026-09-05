from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from github_trending_kb.transaction import ArtifactTransaction, workspace_lock
from github_trending_kb.workspace import WorkspaceLayout
import github_trending_kb.transaction as transaction


class Crash(BaseException):
    pass


class PublicationRecoveryTests(unittest.TestCase):
    def test_an_active_writer_cannot_be_recovered_by_another_writer(self):
        with tempfile.TemporaryDirectory() as temp:
            layout = WorkspaceLayout.discover(Path(temp))
            with workspace_lock(layout):
                with self.assertRaisesRegex(RuntimeError, "active publication"):
                    ArtifactTransaction.recover(layout)

    def test_recovery_rejects_invalid_committed_hash_without_erasing_journal(self):
        with tempfile.TemporaryDirectory() as temp:
            layout = WorkspaceLayout.discover(Path(temp))
            tx = ArtifactTransaction(layout, "2026-09-05")
            tx.stage_text("a.txt", "original")
            original = transaction.atomic_json

            def stop(path, payload):
                original(path, payload)
                if Path(path).parent.name == "commits":
                    raise Crash()

            with patch.object(transaction, "atomic_json", side_effect=stop):
                with self.assertRaises(Crash):
                    tx.commit()
            layout.path("a.txt").write_text("corrupted")
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                ArtifactTransaction.recover(layout)
            self.assertTrue(tx.journal.is_file())

    def test_recovery_preserves_a_durably_committed_generation(self):
        with tempfile.TemporaryDirectory() as temp:
            layout = WorkspaceLayout.discover(Path(temp))
            layout.data_root.mkdir(parents=True)
            target = layout.catalog
            target.write_text("old", encoding="utf-8")
            tx = ArtifactTransaction(layout, "2026-09-05")
            tx.stage_text("catalog.json", "new")
            original = transaction.atomic_json

            def stop_after_commit(path, payload):
                original(path, payload)
                if Path(path).parent.name == "commits":
                    raise Crash()

            with patch.object(
                transaction, "atomic_json", side_effect=stop_after_commit
            ):
                with self.assertRaises(Crash):
                    tx.commit()
            self.assertTrue(ArtifactTransaction.recover(layout))
            self.assertEqual(target.read_text(), "new")
            manifest = json.loads(
                (layout.state_root / "commits/2026-09-05.json").read_text()
            )
            self.assertEqual(
                manifest["files"]["catalog.json"],
                hashlib.sha256(target.read_bytes()).hexdigest(),
            )
            self.assertFalse(ArtifactTransaction.recover(layout))


if __name__ == "__main__":
    unittest.main()
