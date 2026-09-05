from __future__ import annotations
import hashlib, json, sys, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from github_trending_kb.localization import validate_translations, fenced_blocks


def fixture(root, count=1, mode="source-copy"):
    data = root / "workspace"
    (data / "readmes/sources").mkdir(parents=True)
    (data / "daily").mkdir()
    names = [f"example/project{i}" for i in range(count)]
    body = (
        "# 项目说明\n\n## 使用方法\n\n"
        + "这是官方中文说明，介绍项目的输入输出、运行条件以及基本步骤。" * 8
        + "\n\n- 操作\n\n    "
        + chr(96) * 3
        + "sh\n    echo original\n    "
        + chr(96) * 3
        + "\n"
    )
    raw = body.encode()
    sha = hashlib.sha256(raw).hexdigest()
    (data / f"readmes/sources/{sha}.md").write_bytes(raw)
    entries = []
    for name in names:
        url = f"https://github.com/{name}/blob/main/README.md"
        translation = f"readmes/{name.replace('/','__')}.zh-CN.md"
        text = f"---\nfull_name: {name}\nsource_url: {url}\nsource_sha256: {sha}\nlanguage: zh-CN\nmode: {mode}\n---\n\n{body}"
        path = data / translation
        path.write_bytes(text.encode())
        entries.append(
            dict(
                full_name=name,
                source_url=url,
                source_sha256=sha,
                source_artifact=f"readmes/sources/{sha}.md",
                source_bytes=len(raw),
                source_branch="main",
                source_path="README.md",
                mode=mode,
                translation=translation,
                translation_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                translation_bytes=len(body.strip().encode()),
            )
        )
    manifest = dict(schema_version=1, entry_count=len(entries), entries=entries)
    (data / "readmes/manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (data / "catalog.json").write_text(
        json.dumps({"entries": [{"full_name": n} for n in names]})
    )
    (data / "daily/2026-09-05.json").write_text(
        json.dumps(
            dict(
                schema_version=1,
                featured=dict(daily=names, weekly=[], monthly=[]),
                displayed_projects=names,
            )
        )
    )
    return data, manifest


class ReadmeContractTests(unittest.TestCase):
    def test_valid_bound_source_passes(self):
        with tempfile.TemporaryDirectory() as t:
            data, m = fixture(Path(t))
            self.assertEqual(validate_translations(Path(t))["projects"], 1)

    def test_missing_or_corrupted_raw_source_fails(self):
        with tempfile.TemporaryDirectory() as t:
            data, m = fixture(Path(t))
            source = data / m["entries"][0]["source_artifact"]
            source.write_bytes(b"corrupted")
            with self.assertRaisesRegex(ValueError, "SHA-256"):
                validate_translations(Path(t))
            source.unlink()
            with self.assertRaisesRegex(ValueError, "missing source"):
                validate_translations(Path(t))

    def test_duplicate_manifest_entries_fail(self):
        with tempfile.TemporaryDirectory() as t:
            data, m = fixture(Path(t))
            m["entries"] *= 2
            m["entry_count"] = 2
            (data / "readmes/manifest.json").write_text(json.dumps(m))
            with self.assertRaisesRegex(ValueError, "duplicate translation manifest"):
                validate_translations(Path(t))

    def test_identical_body_with_different_frontmatter_is_duplicate(self):
        with tempfile.TemporaryDirectory() as t:
            fixture(Path(t), count=2)
            with self.assertRaisesRegex(ValueError, "duplicate translated README"):
                validate_translations(Path(t))

    def test_changed_indented_code_is_rejected_even_with_updated_translation_hash(self):
        with tempfile.TemporaryDirectory() as t:
            data, m = fixture(Path(t), mode="faithful-translation")
            e = m["entries"][0]
            path = data / e["translation"]
            text = path.read_text(encoding="utf-8").replace(
                "echo original", "echo modified"
            )
            path.write_bytes(text.encode())
            e["translation_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
            (data / "readmes/manifest.json").write_text(json.dumps(m))
            with self.assertRaisesRegex(ValueError, "code blocks differ"):
                validate_translations(Path(t))

    def test_removed_heading_is_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            data, m = fixture(Path(t), mode="faithful-translation")
            e = m["entries"][0]
            path = data / e["translation"]
            text = path.read_text(encoding="utf-8").replace("## 使用方法", "使用方法")
            path.write_bytes(text.encode())
            e["translation_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
            (data / "readmes/manifest.json").write_text(json.dumps(m))
            with self.assertRaisesRegex(ValueError, "heading structure"):
                validate_translations(Path(t))


if __name__ == "__main__":
    unittest.main()
