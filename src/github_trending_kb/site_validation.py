#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

from bs4 import BeautifulSoup

from .github_markdown import media_tags_in_markdown
from .localization import split_translation, validate_translations
from .workspace import WorkspaceLayout


REQUIRED_PROJECT_HEADINGS = [
    "## 一句话介绍",
    "## 项目是做什么的",
    "## 适合谁",
    "## 使用方式",
    "## 主要功能",
    "## 为什么值得关注",
    "## 主要优点",
    "## 明确不足",
    "## License作用域",
    "## 项目价值判断",
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


def validate_site(project_root: Path, site: Path | None = None) -> dict:
    project_root = project_root.resolve()
    root = WorkspaceLayout.discover(project_root).data_root
    site = site or root / "site"
    catalog = json.loads((root / "catalog.json").read_text(encoding="utf-8"))
    try:
        readme_summary = validate_translations(project_root)
    except (KeyError, OSError, TypeError, ValueError) as exc:
        raise SystemExit(f"FAIL Chinese README validation: {exc}")
    project_mds = sorted((root / "repos").glob("*.md"))
    if len(project_mds) != catalog.get("entry_count"):
        raise SystemExit(
            f"FAIL catalog/project Markdown mismatch: {catalog.get('entry_count')} != {len(project_mds)}"
        )
    for path in project_mds:
        text = path.read_text(encoding="utf-8")
        missing = [
            heading for heading in REQUIRED_PROJECT_HEADINGS if heading not in text
        ]
        forbidden = [heading for heading in FORBIDDEN if heading in text]
        if missing or forbidden:
            raise SystemExit(
                f"FAIL {path.name} missing={missing} forbidden={forbidden}"
            )
    daily_mds = sorted((root / "daily").glob("*.md"))
    for daily_path in daily_mds:
        daily = daily_path.read_text(encoding="utf-8")
        for phrase in (
            "淘汰项目与原因",
            "数据缺口",
            "判断边界",
            "今日一句话结论",
            "AI主题候选",
            "NEW_HOT｜近期新项目",
            "REVIVED_HOT｜重新走红项目",
        ):
            if phrase in daily:
                raise SystemExit(
                    f"FAIL {daily_path.name} contains forbidden phrase: {phrase}"
                )
        for name in ("日榜精选", "周榜精选", "月榜精选"):
            if name not in daily:
                raise SystemExit(f"FAIL {daily_path.name} missing section: {name}")

    html_files = sorted(site.rglob("*.html"))
    expected_html = 2 + len(daily_mds) + len(project_mds)
    if len(html_files) != expected_html:
        raise SystemExit(
            f"FAIL expected {expected_html} HTML files, got {len(html_files)}"
        )
    manifest_path = root / "readmes" / "manifest.json"
    translated_names = []
    readme_entries = {}
    if manifest_path.is_file():
        readme_entries = {
            e["full_name"]: e
            for e in json.loads(manifest_path.read_text(encoding="utf-8-sig")).get(
                "entries", []
            )
        }
        translated_names = list(readme_entries)
    for name in translated_names:
        detail_path = site / "repos" / f"{name.replace('/', '__')}.html"
        detail_text = detail_path.read_text(encoding="utf-8")
        if 'id="chinese-readme"' not in detail_text:
            raise SystemExit(
                f"FAIL project detail lacks embedded Chinese README: {name}"
            )
        readme_entry = readme_entries[name]
        _, readme_body = split_translation(
            (root / readme_entry["translation"]).read_text(encoding="utf-8-sig")
        )
        expected_media = media_tags_in_markdown(readme_body)
        detail_soup = BeautifulSoup(detail_text, "html.parser")
        readme_section = detail_soup.find(id="chinese-readme")
        if readme_section is None:
            raise SystemExit(
                f"FAIL project detail lacks embedded Chinese README: {name}"
            )
        for field in ("source_sha256", "translation_sha256"):
            if (
                readme_section.get("data-" + field.replace("_", "-"))
                != readme_entry[field]
            ):
                raise SystemExit(f"FAIL project detail contains a stale README: {name}")
        body_node = readme_section.select_one(".localized-readme-body")
        if body_node is None or hashlib.sha256(
            str(body_node).encode("utf-8")
        ).hexdigest() != readme_section.get("data-rendered-sha256"):
            raise SystemExit(f"FAIL rendered README content changed: {name}")
        visible_section = BeautifulSoup(str(readme_section), "html.parser")
        for code_node in visible_section.find_all(["pre", "code"]):
            code_node.decompose()
        visible_html = str(visible_section).lower()
        for tag in ("picture", "img", "video", "details", "table"):
            if tag in expected_media and readme_section.find(tag) is None:
                raise SystemExit(
                    f"FAIL project detail dropped README HTML tag <{tag}>: {name}"
                )
            if f"&lt;{tag}" in visible_html:
                raise SystemExit(
                    f"FAIL project detail escaped README HTML tag <{tag}>: {name}"
                )
    broken = []
    for path in html_files:
        parser_obj = LinkParser()
        parser_obj.feed(path.read_text(encoding="utf-8"))
        for href in parser_obj.links:
            parts = urlsplit(href)
            if parts.scheme in {"http", "https", "mailto"} or href.startswith("#"):
                continue
            virtual = root / "site" / path.relative_to(site)
            logical_target = (virtual.parent / unquote(parts.path)).resolve()
            if logical_target.is_relative_to((root / "site").resolve()):
                target = site / logical_target.relative_to((root / "site").resolve())
            else:
                target = logical_target
            if not target.exists():
                broken.append(f"{path.relative_to(site)} -> {href}")
    if broken:
        raise SystemExit("FAIL broken links: " + "; ".join(broken[:20]))
    directory = site / "catalog.html"
    if not directory.is_file():
        raise SystemExit("FAIL missing HTML catalog")
    soup = BeautifulSoup(directory.read_text(encoding="utf-8"), "html.parser")
    directory_names = [
        tag.get("data-name") for tag in soup.select("[data-catalog-item]")
    ]
    if len(directory_names) != len(set(directory_names)) or set(directory_names) != {
        e["full_name"] for e in catalog["entries"]
    }:
        raise SystemExit("FAIL HTML catalog coverage mismatch")
    return dict(
        markdown_projects=len(project_mds),
        readme_translations=readme_summary["chinese_files"],
        daily_reports=len(daily_mds),
        html_pages=len(html_files),
        broken_links=0,
        catalog_accessible=len(directory_names),
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    result = validate_site(args.root)
    print("SITE VALIDATE PASS " + " ".join(f"{k}={v}" for k, v in result.items()))


if __name__ == "__main__":
    main()
