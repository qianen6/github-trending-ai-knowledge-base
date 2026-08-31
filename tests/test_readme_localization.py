from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def translation_text(full_name: str, source_sha256: str) -> str:
    body = (
        "这是面向中文读者整理的项目说明，介绍项目目标、主要能力、安装方式、基本用法和使用限制。"
        "用户可以根据这里保留的命令完成安装，并结合原始项目文档核对最新参数。"
        "本地化内容保留必要的技术名称、命令和链接，同时使用中文解释每一步的目的与输出。"
    )
    return (
        "---\n"
        f"full_name: {full_name}\n"
        "source_url: https://github.com/example/project/blob/main/README.md\n"
        f"source_sha256: {source_sha256}\n"
        "language: zh-CN\n"
        "mode: faithful-translation\n"
        "---\n\n"
        "# 中文 README\n\n"
        "<p align=\"center\"><picture><source media=\"(prefers-color-scheme: dark)\" srcset=\"https://example.com/dark.svg\"><img src=\"https://example.com/light.svg\" alt=\"示例图片\" width=\"200\"></picture></p>\n\n"
        "<div align=\"center\"><video src=\"https://example.com/demo.mp4\" controls></video></div>\n\n"
        "<details open><summary>展开详情</summary><table><tr><td>中文内容</td></tr></table></details>\n\n"
        "<details>\n<summary>嵌套 Markdown 示例</summary>\n\n"
        "| 主题 | 徽章 |\n|---|---|\n"
        "| 深色 | <img src=\"https://example.com/nested.svg\" alt=\"嵌套图片\" width=\"120\"> |\n\n"
        "```html\n<img src=\"https://example.com/code-example.svg\">\n```\n"
        "</details>\n\n"
        "## 项目简介\n\n"
        f"{body}\n\n"
        "## 安装与使用\n\n"
        "[安装说明](./docs/install.md)\n\n"
        "<a href=\"./LICENSE\">许可证</a>\n\n"
        "[![许可证徽章](https://img.shields.io/badge/license-MIT-green.svg)](./LICENSE)\n\n"
        "```bash\npip install example\n```\n"
    )


class ReadmeLocalizationTests(unittest.TestCase):
    def test_translation_validator_and_detail_embedding(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            for name in ("daily", "repos", "readmes", "site", "incoming", "evaluations"):
                (root / name).mkdir(parents=True, exist_ok=True)

            full_name = "example/project"
            slug = "example__project"
            source_sha256 = "a" * 64
            translation_path = root / "readmes" / f"{slug}.zh-CN.md"
            translation_path.write_text(translation_text(full_name, source_sha256), encoding="utf-8")
            translation_sha256 = hashlib.sha256(translation_path.read_bytes()).hexdigest()
            translation_raw = translation_path.read_text(encoding="utf-8")
            translation_body = translation_raw[translation_raw.find("\n---\n", 4) + 5 :].strip()
            manifest = {
                "schema_version": 1,
                "entry_count": 1,
                "entries": [
                    {
                        "full_name": full_name,
                        "source_url": "https://github.com/example/project/blob/main/README.md",
                        "source_sha256": source_sha256,
                        "source_branch": "main",
                        "source_path": "README.md",
                        "source_bytes": 1000,
                        "mode": "faithful-translation",
                        "translation": f"readmes/{slug}.zh-CN.md",
                        "translation_sha256": translation_sha256,
                        "translation_bytes": len(translation_body.encode("utf-8")),
                    }
                ],
            }
            (root / "readmes" / "manifest.json").write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            card = (
                "# example/project\n\n"
                "## 一句话介绍\n\n示例项目。\n\n"
                "## 项目是做什么的\n\n处理示例输入并生成示例输出。\n\n"
                "## 适合谁\n\n- 示例用户\n\n"
                "## 使用方式\n\n通过示例命令启动。\n\n"
                "## 主要功能\n\n- 处理示例任务\n- 输出示例结果\n\n"
                "## 为什么值得关注\n\n提供可复现的示例流程。\n\n"
                "## 主要优点\n\n- 接口简单\n- 输出明确\n\n"
                "## 明确不足\n\n- 仅用于测试场景\n\n"
                "## License作用域\n\nMIT：覆盖示例代码。\n\n"
                "## 项目价值判断\n\n用于验证渲染流程。\n\n"
                "## Trending表现与综合评分\n\n示例评分。\n\n"
                "## 项目链接\n\nhttps://github.com/example/project\n"
            )
            (root / "repos" / f"{slug}.md").write_text(card, encoding="utf-8")
            catalog = {
                "schema_version": 4,
                "updated_at": "2026-08-30",
                "candidate_source": "GitHub Trending",
                "dedupe_key": "full_name",
                "entry_count": 1,
                "entries": [
                    {
                        "full_name": full_name,
                        "card": f"repos/{slug}.md",
                    }
                ],
            }
            (root / "catalog.json").write_text(json.dumps(catalog, ensure_ascii=False), encoding="utf-8")
            (root / "index.md").write_text("# 索引\n", encoding="utf-8")
            (root / "daily" / "2026-08-30.md").write_text(
                "# 日报\n\n## 日榜精选\n\n### example/project\n\n示例。\n\n## 周榜精选\n\n## 月榜精选\n",
                encoding="utf-8",
            )
            (root / "incoming" / "2026-08-30.json").write_text(
                json.dumps({"pages": [], "candidate_pool": {"raw_candidate_count": 1}}), encoding="utf-8"
            )
            (root / "evaluations" / "2026-08-30.json").write_text(
                json.dumps({"entries": []}), encoding="utf-8"
            )

            validate = subprocess.run(
                [sys.executable, str(REPO_ROOT / "scripts" / "readme_translations.py"), "validate", "--root", str(root)],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(validate.returncode, 0, validate.stderr)
            self.assertIn("README VALIDATE PASS projects=1", validate.stdout)

            build = subprocess.run(
                [sys.executable, str(REPO_ROOT / "scripts" / "build_site.py"), "--root", str(root)],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(build.returncode, 0, build.stderr)
            detail = (root / "site" / "repos" / f"{slug}.html").read_text(encoding="utf-8")
            self.assertIn('id="chinese-readme"', detail)
            self.assertIn("面向中文读者整理的项目说明", detail)
            self.assertIn("<pre><code", detail)
            self.assertIn("https://github.com/example/project/blob/main/docs/install.md", detail)
            self.assertIn("https://github.com/example/project/blob/main/LICENSE", detail)
            self.assertIn("<picture>", detail)
            self.assertIn("<img", detail)
            self.assertIn("<video", detail)
            self.assertIn("<details", detail)
            self.assertIn('<td><img alt="嵌套图片"', detail)
            self.assertNotIn("&lt;picture", detail)

            site_validate = subprocess.run(
                [sys.executable, str(REPO_ROOT / "scripts" / "validate_site.py"), "--root", str(root)],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(site_validate.returncode, 0, site_validate.stderr + site_validate.stdout)

            translation_path.unlink()
            missing = subprocess.run(
                [sys.executable, str(REPO_ROOT / "scripts" / "readme_translations.py"), "validate", "--root", str(root)],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(missing.returncode, 0)
            self.assertIn("missing translation", missing.stderr + missing.stdout)


if __name__ == "__main__":
    unittest.main()
