from __future__ import annotations
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from github_trending_kb.localization import validate_translation


class ReadmeIntegrityTests(unittest.TestCase):
    def test_source_copy_must_match_the_actual_source(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            source = (
                "# 标题\n\n## 使用\n\n"
                + "这是官方中文原文，介绍项目的用途和使用条件。" * 8
            )
            body = source.replace("官方中文原文", "被改写的内容")
            digest = hashlib.sha256(source.encode()).hexdigest()
            (folder / "sources").mkdir()
            (folder / "sources" / f"{digest}.md").write_bytes(source.encode("utf-8"))
            path = folder / "example__project.zh-CN.md"
            url = "https://github.com/example/project/blob/main/README.md"
            path.write_text(
                f"---\nfull_name: example/project\nsource_url: {url}\nsource_sha256: {digest}\nlanguage: zh-CN\nmode: source-copy\n---\n\n{body}\n",
                encoding="utf-8",
            )
            entry = dict(
                full_name="example/project",
                source_url=url,
                source_sha256=digest,
                source_bytes=len(source.encode()),
                translation_bytes=len(body.encode()),
                mode="source-copy",
            )
            with self.assertRaisesRegex(ValueError, "source-copy"):
                validate_translation(path, entry)


if __name__ == "__main__":
    unittest.main()
