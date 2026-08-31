from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from github_trending_kb.collector import (  # noqa: E402
    FixtureFetchAdapter,
    TrendingCollector,
    parse_number,
    parse_trending_html,
    trending_page_matrix,
)


HTML = """
<article class="Box-row">
  <h2><a href="/example/project">example / project</a></h2>
  <p class="col-9">Example description</p>
  <span itemprop="programmingLanguage">Python</span>
  <a href="/example/project/stargazers">1,234</a>
  <a href="/example/project/forks">56</a>
  <span class="float-sm-right">78 stars today</span>
  <span class="d-inline-block"><img alt="@builder"></span>
</article>
"""


class CollectionTests(unittest.TestCase):
    def test_matrix_and_html_parser(self) -> None:
        specs = trending_page_matrix()
        self.assertEqual(len(specs), 21)
        self.assertEqual(len({(item.scope, item.period) for item in specs}), 21)
        entry = parse_trending_html(HTML)[0]
        self.assertEqual(entry["full_name"], "example/project")
        self.assertEqual(entry["total_stars"], 1234)
        self.assertEqual(entry["period_stars"], 78)
        self.assertEqual(entry["built_by"], ["builder"])
        self.assertEqual(parse_number("10,384 stars this month"), 10384)
        self.assertEqual(parse_number("1.2k stars today"), 1200)

    def test_fixture_adapter_supports_deterministic_replay(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            responses = {spec.url: HTML for spec in trending_page_matrix()}
            collector = TrendingCollector(root, FixtureFetchAdapter(responses))
            first = collector.collect(date(2026, 8, 31), max_workers=4)
            self.assertEqual(first["page_count"], 21)
            self.assertEqual(first["successful_pages"], 21)
            self.assertEqual(first["candidate_count"], 1)
            self.assertEqual(
                len(list((root / "trending" / "html" / "2026-08-31").glob("*.html"))),
                21,
            )

            replay = TrendingCollector(root, FixtureFetchAdapter({})).collect(
                date(2026, 8, 31), max_workers=4
            )
            self.assertEqual(replay["successful_pages"], 21)
            self.assertEqual(replay["repository_names"], ["example/project"])

    def test_retry_adapter_recovers_without_refetching_saved_pages(self) -> None:
        class FlakyAdapter:
            def __init__(self) -> None:
                self.calls = 0

            def fetch(self, url, headers, timeout):
                self.calls += 1
                if self.calls == 1:
                    raise OSError("temporary failure")
                return HTML.encode()

        with tempfile.TemporaryDirectory() as temp:
            adapter = FlakyAdapter()
            collector = TrendingCollector(Path(temp), adapter, retries=2, retry_delay=0)
            page = collector.collect_page(trending_page_matrix()[0], date(2026, 8, 31), refresh=True)
            self.assertEqual(page["status"], "success")
            self.assertEqual(adapter.calls, 2)


if __name__ == "__main__":
    unittest.main()
