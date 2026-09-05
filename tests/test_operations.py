from __future__ import annotations
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from datetime import date
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from github_trending_kb.operations import verify_and_build, prepare_batch, publish_batch
from github_trending_kb.proof_archive import archive_proofs, restore_archive
from github_trending_kb.bootstrap import initialize
from test_site_features import catalog_fixture
from test_trending_engine import repo, pages
from github_trending_kb.transaction import ArtifactTransaction
import github_trending_kb.proof_archive as archive_module


def docs(root):
    for name in ("README.md", "WORKFLOW.md", "SCREENING_RULES.md"):
        (root / name).write_text("# test", encoding="utf-8")


class OperationsTests(unittest.TestCase):
    def test_commit_referenced_file_changes_invalidate_cached_engine_check(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            catalog_fixture(root)
            docs(root)
            layout = initialize(root)
            tx = ArtifactTransaction(layout, "2026-09-05")
            tx.stage_text("rejections/integrity.json", "original")
            tx.commit()
            verify_and_build(root)
            layout.path("rejections/integrity.json").write_text("damaged")
            with self.assertRaisesRegex(ValueError, "committed artifact changed"):
                verify_and_build(root)

    def test_archive_preserves_files_created_after_manifest_write(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            layout = initialize(root)
            target = layout.path("proof/run-2026-08-01/rollback-test")
            target.mkdir(parents=True)
            (target / "old.txt").write_text("old")
            original = archive_module.atomic_json

            def late_file(path, payload):
                original(path, payload)
                if path.name == "rollback-test.archive.json":
                    (target / "late.txt").write_text("late")

            with patch.object(archive_module, "atomic_json", side_effect=late_file):
                with self.assertRaisesRegex(ValueError, "source retained"):
                    archive_proofs(root, date(2026, 9, 5), True)
            self.assertEqual((target / "late.txt").read_text(), "late")
            self.assertEqual((target / "old.txt").read_text(), "old")

    def test_resumed_verification_reuses_only_unchanged_stages(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            catalog_fixture(root)
            docs(root)
            first = verify_and_build(root)
            self.assertEqual(first["passed"], 4)
            second = verify_and_build(root)
            self.assertEqual(second["reused"], 4)
            (root / "workspace/site/catalog.html").write_text(
                "damaged", encoding="utf-8"
            )
            third = verify_and_build(root)
            self.assertEqual(third["stages"]["build"]["status"], "passed")
            self.assertIn(
                "data-catalog-item",
                (root / "workspace/site/catalog.html").read_text(encoding="utf-8"),
            )

    def test_missing_readmes_fail_before_publishing_new_data(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            layout = initialize(root)
            docs(root)
            original = layout.catalog.read_bytes()
            batch = {
                "schema_version": 4,
                "capture_date": "2026-08-27",
                "captured_at": "2026-08-27T09:00:00+08:00",
                "candidate_pool": {
                    "description": "官方Trending候选",
                    "dedupe_key": "full_name",
                    "raw_candidate_count": 2,
                    "evaluated_candidate_count": 2,
                },
                "pages": pages(),
                "repositories": [
                    repo("example/new-hot", "2026-08-01T00:00:00Z"),
                    repo("example/revived-hot", "2020-01-01T00:00:00Z"),
                ],
            }
            input_path = layout.path("proof/input.json")
            input_path.parent.mkdir(parents=True, exist_ok=True)
            input_path.write_text(
                json.dumps(batch, ensure_ascii=False), encoding="utf-8"
            )
            prepared = prepare_batch(root, input_path)
            self.assertTrue(Path(prepared["staging_root"]).exists())
            with self.assertRaises(ValueError):
                publish_batch(root, input_path)
            self.assertEqual(layout.catalog.read_bytes(), original)
            self.assertFalse((layout.state_root / "commits/2026-08-27.json").exists())
            # A live README update after prepare requires explicit selection.
            live_change = layout.readmes / "new-note.txt"
            live_change.write_text("live update")
            with self.assertRaisesRegex(ValueError, "live README changed"):
                publish_batch(root, input_path)
            live_change.unlink()
            stage = Path(prepared["staging_root"])
            edition = json.loads(
                (stage / "workspace/daily/2026-08-27.json").read_text()
            )
            entries = []
            for name in edition["displayed_projects"]:
                body = (
                    "# 项目说明\n\n## 使用\n\n"
                    + "这是官方中文说明，记录项目输入输出以及完整的使用条件。" * 8
                )
                raw = body.encode("utf-8")
                sha = hashlib.sha256(raw).hexdigest()
                source = stage / f"workspace/readmes/sources/{sha}.md"
                source.parent.mkdir(parents=True, exist_ok=True)
                source.write_bytes(raw)
                url = f"https://github.com/{name}/blob/main/README.md"
                translation = f"readmes/{name.replace('/','__')}.zh-CN.md"
                text = f"---\nfull_name: {name}\nsource_url: {url}\nsource_sha256: {sha}\nlanguage: zh-CN\nmode: source-copy\n---\n\n{body}\n"
                translated = stage / "workspace" / translation
                translated.write_bytes(text.encode())
                entries.append(
                    dict(
                        full_name=name,
                        source_url=url,
                        source_sha256=sha,
                        source_artifact=f"readmes/sources/{sha}.md",
                        source_bytes=len(raw),
                        source_branch="main",
                        source_path="README.md",
                        mode="source-copy",
                        translation=translation,
                        translation_sha256=hashlib.sha256(
                            translated.read_bytes()
                        ).hexdigest(),
                        translation_bytes=len(raw),
                    )
                )
            (stage / "workspace/readmes/manifest.json").write_text(
                json.dumps(
                    dict(schema_version=1, entry_count=len(entries), entries=entries)
                ),
                encoding="utf-8",
            )
            result = publish_batch(root, input_path)
            self.assertGreater(result["committed_files"], 0)
            self.assertNotEqual(layout.catalog.read_bytes(), original)
            self.assertTrue((layout.site / "catalog.html").is_file())
            marker = json.loads(
                (layout.state_root / "commits/2026-08-27.json").read_text()
            )
            self.assertIn("site/catalog.html", marker["files"])
            self.assertIn("readmes/manifest.json", marker["files"])

    def test_archive_round_trip_preserves_every_byte(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            layout = initialize(root)
            old = layout.path("proof/run-2026-08-01/rollback-test")
            old.mkdir(parents=True)
            (old / "payload.bin").write_bytes(b"original" * 2048)
            latest = layout.path("proof/run-2026-09-05/rollback-test")
            latest.mkdir(parents=True)
            (latest / "keep.txt").write_text("keep")
            source = layout.path("proof/run-2026-08-01/sources/official.md")
            source.parent.mkdir()
            source.write_text("official")
            plan = archive_proofs(root, date(2026, 9, 5))
            self.assertEqual(plan["candidates"], 1)
            self.assertTrue(old.exists())
            result = archive_proofs(root, date(2026, 9, 5), True)
            self.assertGreater(result["saved_bytes"], 0)
            self.assertFalse(old.exists())
            restored = layout.path("proof/restored-check")
            restore_archive(
                Path(result["entries"][0]["archive"]), restored, layout.data_root
            )
            self.assertEqual(
                (restored / "payload.bin").read_bytes(), b"original" * 2048
            )
            self.assertTrue(source.is_file())
            self.assertTrue(latest.is_dir())

    def test_archive_rejects_active_references(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            layout = initialize(root)
            old = layout.path("proof/run-2026-08-01/rollback-test")
            old.mkdir(parents=True)
            (old / "x").write_text("x")
            layout.catalog.write_text(json.dumps({"reference": str(old / "x")}))
            with self.assertRaisesRegex(ValueError, "active manifests"):
                archive_proofs(root, date(2026, 9, 5), True)
            self.assertTrue(old.exists())


if __name__ == "__main__":
    unittest.main()
