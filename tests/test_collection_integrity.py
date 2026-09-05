from __future__ import annotations
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from github_trending_kb.collector import (
    TrendingCollector,
    FixtureFetchAdapter,
    parse_trending_html,
    trending_page_matrix,
)


class CollectionIntegrityTests(unittest.TestCase):
    def test_recognized_empty_board_is_valid(self):
        self.assertEqual(
            parse_trending_html(
                "<main><h1>Trending</h1><p>It looks like we don't have any trending repositories for this period.</p></main>"
            ),
            [],
        )

    def test_partially_changed_rows_are_not_silently_dropped(self):
        with self.assertRaises(ValueError):
            parse_trending_html(
                '<article class="Box-row"><h2><a href="/a/b">a/b</a></h2></article><article class="Box-row"><h3>changed</h3></article>'
            )

    def test_failed_cached_html_is_refetched_on_resume(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            day = date(2026, 9, 5)
            spec = trending_page_matrix()[0]
            broken = root / "workspace/trending/html/2026-09-05" / f"{spec.slug}.html"
            broken.parent.mkdir(parents=True)
            broken.write_text("<h1>temporary failure</h1>")
            body = '<article class="Box-row"><h2><a href="/a/b">a/b</a></h2></article>'
            result = TrendingCollector(
                root, FixtureFetchAdapter({spec.url: body}), retry_delay=0
            ).collect_page(spec, day, False)
            self.assertEqual(result["status"], "success")
            self.assertEqual(result["entries"][0]["full_name"], "a/b")

    def test_unrecognized_200_html_is_not_a_successful_empty_board(self):
        with self.assertRaises(ValueError):
            parse_trending_html("<html><h1>Temporary service unavailable</h1></html>")

    def test_corrupt_cache_refetches_only_invalid_records(self):
        class Counting(FixtureFetchAdapter):
            def __init__(self, responses):
                super().__init__(responses)
                self.calls = []

            def fetch(self, url, headers, timeout):
                self.calls.append(url)
                return super().fetch(url, headers, timeout)

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            urls = [
                "https://api.github.com/repos/example/project" + s
                for s in ("", "/readme", "/license", "/contents")
            ]
            first = TrendingCollector(
                root, FixtureFetchAdapter({u: "{}" for u in urls})
            ).collect_evidence("example/project", date(2026, 9, 5))
            for record in first["records"]:
                if record["kind"] == "readme":
                    (root / "workspace" / record["path"]).unlink()
                if record["kind"] == "repository":
                    (root / "workspace" / record["path"]).write_text('{"corrupt":true}')
            adapter = Counting({u: "{}" for u in urls})
            fresh = TrendingCollector(root, adapter).collect_evidence(
                "example/project", date(2026, 9, 5)
            )
            self.assertEqual(set(adapter.calls), set(urls[:2]))
            self.assertTrue(all(r["status"] == "success" for r in fresh["records"]))


if __name__ == "__main__":
    unittest.main()
