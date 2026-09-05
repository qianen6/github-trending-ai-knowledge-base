from __future__ import annotations
import json
import subprocess
import sys
import tempfile
import unittest
import hashlib
import shutil
from pathlib import Path
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from github_trending_kb.bootstrap import initialize
from github_trending_kb.site_validation import REQUIRED_PROJECT_HEADINGS
from github_trending_kb.site_builder import build_site
from github_trending_kb.catalog_view import CATALOG_SCRIPT
from github_trending_kb.render_cache import RenderCache


def catalog_fixture(root):
    layout = initialize(root)
    entries = []
    for name, category, language in [
        ("example/tool", "数据分析", "Python"),
        ("example/app", "开发工具", "Rust"),
    ]:
        slug = name.replace("/", "__")
        card = (
            "# "
            + name
            + "\n\n"
            + "\n\n".join(
                h + "\n\n这里是项目的中文说明。" for h in REQUIRED_PROJECT_HEADINGS
            )
        )
        (layout.repos / f"{slug}.md").write_text(card, encoding="utf-8")
        entries.append(
            dict(
                full_name=name,
                card=f"repos/{slug}.md",
                one_line="示例项目",
                category=category,
                language=language,
                last_evaluated="2026-09-05",
            )
        )
    layout.catalog.write_text(
        json.dumps(dict(entry_count=2, entries=entries), ensure_ascii=False),
        encoding="utf-8",
    )
    return layout


class SiteFeatureTests(unittest.TestCase):
    def test_failed_staged_validation_keeps_previous_site(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            layout = catalog_fixture(root)
            build_site(root)
            old = {
                p.relative_to(layout.site): p.read_bytes()
                for p in layout.site.rglob("*")
                if p.is_file()
            }
            (layout.repos / "example__tool.md").write_text("# broken", encoding="utf-8")
            with self.assertRaises(SystemExit):
                build_site(root)
            self.assertEqual(
                old,
                {
                    p.relative_to(layout.site): p.read_bytes()
                    for p in layout.site.rglob("*")
                    if p.is_file()
                },
            )

    def test_incremental_and_full_builds_are_identical(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            layout = catalog_fixture(root)
            build_site(root)
            again = build_site(root)
            self.assertEqual(again["rendered"], 0)
            cached = {
                p.relative_to(layout.site): p.read_bytes()
                for p in layout.site.rglob("*")
                if p.is_file()
            }
            build_site(root, use_cache=False)
            self.assertEqual(
                cached,
                {
                    p.relative_to(layout.site): p.read_bytes()
                    for p in layout.site.rglob("*")
                    if p.is_file()
                },
            )

    def test_corrupted_render_cache_is_regenerated(self):
        with tempfile.TemporaryDirectory() as temp:
            cache = RenderCache(Path(temp))
            original = cache.render("# original")
            path = next(Path(temp).glob("*.json"))
            payload = json.loads(path.read_text())
            payload["html"] = "damaged"
            path.write_text(json.dumps(payload))
            self.assertEqual(cache.render("# original"), original)
            self.assertEqual(cache.hits, 0)

    @unittest.skipUnless(
        shutil.which("node"), "Node is needed for the standalone offline filter test"
    )
    def test_offline_filter_handles_case_chinese_and_combined_filters(self):
        script = (
            CATALOG_SCRIPT
            + """
const match=module.exports.matchesProject;
const p={search:"Example/Tool 数据分析 Python",category:"数据分析",language:"Python"};
if (!match(p,{query:"example 数据",category:"数据分析",language:"Python"})) process.exit(1);
if (match(p,{query:"absent"})) process.exit(2);
if (match(p,{query:"",language:"Rust"})) process.exit(3);
if (!match(p,{query:""})) process.exit(4);
console.log("FILTER PASS");
"""
        )
        result = subprocess.run(["node", "-e", script], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("FILTER PASS", result.stdout)

    def test_every_project_has_a_static_catalog_link(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            layout = catalog_fixture(root)
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts/build_site.py"),
                    "--root",
                    str(root),
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertTrue((layout.site / "catalog.html").is_file())
            soup = BeautifulSoup(
                (layout.site / "catalog.html").read_text(encoding="utf-8"),
                "html.parser",
            )
            self.assertEqual(len(soup.select("[data-catalog-item]")), 2)
            self.assertTrue(soup.find("input", id="catalog-query"))
            self.assertTrue(soup.find("select", id="catalog-category"))
            self.assertTrue(soup.find("select", id="catalog-language"))
            self.assertTrue(
                all(
                    not tag.has_attr("hidden")
                    for tag in soup.select("[data-catalog-item]")
                )
            )


if __name__ == "__main__":
    unittest.main()
