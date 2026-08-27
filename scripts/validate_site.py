#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit


REQUIRED_PROJECT_HEADINGS = [
    "## 一句话介绍",
    "## 项目是做什么的",
    "## 适合谁",
    "## 使用方式",
    "## 主要功能",
    "## 为什么值得关注",
    "## 主要优点",
    "## 明确不足",
    "## AI价值判断",
    "## Trending表现与综合评分",
    "## 项目链接",
]

FORBIDDEN = [
    "## 数据与状态如何保存",
    "## 模型和供应商如何接入",
    "## 错误、重试与恢复",
    "## 安装与依赖成本",
    "## 测试、CI与Release",
    "## License双轨",
    "## 与同类项目的区别",
    "## 核心调用链",
    "## 核心源码证据",
]


class LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag not in {"a", "link"}:
            return
        values = dict(attrs)
        key = "href"
        if values.get(key):
            self.links.append(values[key] or "")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    catalog = json.loads((root / "catalog.json").read_text(encoding="utf-8"))
    project_mds = sorted((root / "repos").glob("*.md"))
    if len(project_mds) != catalog.get("entry_count"):
        raise SystemExit(f"FAIL catalog/project Markdown mismatch: {catalog.get('entry_count')} != {len(project_mds)}")
    for path in project_mds:
        text = path.read_text(encoding="utf-8")
        missing = [heading for heading in REQUIRED_PROJECT_HEADINGS if heading not in text]
        forbidden = [heading for heading in FORBIDDEN if heading in text]
        if missing or forbidden:
            raise SystemExit(f"FAIL {path.name} missing={missing} forbidden={forbidden}")
    daily_mds = sorted((root / "daily").glob("*.md"))
    for daily_path in daily_mds:
        daily = daily_path.read_text(encoding="utf-8")
        for phrase in ("淘汰项目与原因", "数据缺口", "判断边界", "今日一句话结论"):
            if phrase in daily:
                raise SystemExit(f"FAIL {daily_path.name} contains forbidden phrase: {phrase}")
        for name in ("NEW_HOT｜近期新项目", "REVIVED_HOT｜重新走红项目"):
            if name not in daily:
                raise SystemExit(f"FAIL {daily_path.name} missing section: {name}")

    html_files = sorted((root / "site").rglob("*.html"))
    expected_html = 1 + len(daily_mds) + len(project_mds)
    if len(html_files) != expected_html:
        raise SystemExit(f"FAIL expected {expected_html} HTML files, got {len(html_files)}")
    broken = []
    for path in html_files:
        parser_obj = LinkParser()
        parser_obj.feed(path.read_text(encoding="utf-8"))
        for href in parser_obj.links:
            parts = urlsplit(href)
            if parts.scheme in {"http", "https", "mailto"} or href.startswith("#"):
                continue
            target = (path.parent / unquote(parts.path)).resolve()
            if not target.exists():
                broken.append(f"{path.relative_to(root)} -> {href}")
    if broken:
        raise SystemExit("FAIL broken links: " + "; ".join(broken[:20]))
    print(f"SITE VALIDATE PASS markdown_projects={len(project_mds)} daily_reports={len(daily_mds)} html_pages={len(html_files)} broken_links=0")


if __name__ == "__main__":
    main()
