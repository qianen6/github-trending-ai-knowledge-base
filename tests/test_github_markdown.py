from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from github_trending_kb.github_markdown import (  # noqa: E402
    absolutize_markdown_links,
    media_tags_in_markdown,
    render_markdown,
)


class GitHubMarkdownTests(unittest.TestCase):
    def test_links_rendering_and_sanitization_share_one_module(self) -> None:
        source = """
<details><summary>展开</summary>

![图](./assets/demo.png)

<video src="./demo.mp4" controls></video>
<script>alert(1)</script>
</details>
"""
        absolute = absolutize_markdown_links(source, "example/project", "main", "README.md")
        self.assertIn("raw.githubusercontent.com/example/project/main/assets/demo.png", absolute)
        html = render_markdown(absolute)
        self.assertIn("<details", html)
        self.assertIn("<video", html)
        self.assertNotIn("<script", html)
        self.assertEqual(media_tags_in_markdown(source), {"details", "img", "video"})


if __name__ == "__main__":
    unittest.main()
