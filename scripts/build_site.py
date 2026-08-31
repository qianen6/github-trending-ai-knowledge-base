#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import re
from datetime import date
from pathlib import Path

import bleach
import markdown as markdown_lib
from bs4 import BeautifulSoup
from markdown.extensions.toc import slugify_unicode

from readme_translations import absolutize_markdown_links, split_translation

from trending_engine import PERIOD_LABELS, PERIOD_ORDER, evaluation_value, select_period_features


STYLE = r"""
:root {
  color-scheme: light dark;
  --bg: #f7f7f4;
  --surface: #ffffff;
  --ink: #1b1d1f;
  --muted: #62676d;
  --line: #d9dddf;
  --accent: #176b5b;
  --daily: #a54d18;
  --weekly: #176b5b;
  --monthly: #3a5a98;
  --code: #eef1ef;
  --shadow: 0 1px 2px rgba(20, 24, 28, 0.04);
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #111315;
    --surface: #181b1e;
    --ink: #eef1f3;
    --muted: #aab0b5;
    --line: #30363b;
    --accent: #70c7b2;
    --daily: #f0a36f;
    --weekly: #70c7b2;
    --monthly: #9eb7f2;
    --code: #23272a;
    --shadow: none;
  }
}
* { box-sizing: border-box; }
html { scroll-behavior: auto; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--ink);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans SC", "Microsoft YaHei", sans-serif;
  line-height: 1.7;
}
a { color: var(--accent); text-decoration-thickness: 1px; text-underline-offset: 3px; }
a:hover { text-decoration-thickness: 2px; }
.shell { width: min(1120px, calc(100% - 64px)); margin: 0 auto; }
.reading { width: min(760px, calc(100% - 40px)); margin: 0 auto; }
.topbar { border-bottom: 1px solid var(--line); background: color-mix(in srgb, var(--bg) 94%, transparent); }
.nav { min-height: 58px; display: flex; align-items: center; justify-content: space-between; gap: 20px; }
.brand { color: var(--ink); font-weight: 720; text-decoration: none; letter-spacing: -0.02em; }
.navlinks { display: flex; gap: 18px; flex-wrap: wrap; font-size: 14px; }
.navlinks a { color: var(--muted); text-decoration: none; }
main { padding: 56px 0 80px; }
.eyebrow { color: var(--accent); font-size: 13px; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; }
h1, h2, h3 { line-height: 1.22; letter-spacing: -0.025em; }
h1 { font-size: clamp(34px, 6vw, 62px); margin: 10px 0 18px; }
h2 { font-size: clamp(24px, 3.2vw, 34px); margin: 48px 0 18px; }
h3 { font-size: 19px; margin: 0; }
.lede { color: var(--muted); max-width: 720px; font-size: 18px; }
.stats { margin: 32px 0 48px; display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); border: 1px solid var(--line); background: var(--surface); }
.stat { padding: 18px 20px; border-right: 1px solid var(--line); }
.stat:last-child { border-right: 0; }
.stat strong { display: block; font: 700 24px/1.1 ui-monospace, SFMono-Regular, Consolas, monospace; font-variant-numeric: tabular-nums; }
.stat span { color: var(--muted); font-size: 13px; }
.section-head { display: flex; align-items: end; justify-content: space-between; gap: 20px; margin-bottom: 18px; border-bottom: 1px solid var(--line); padding-bottom: 12px; }
.section-head h2 { margin: 0; }
.section-head p { margin: 0; color: var(--muted); font-size: 14px; }
.grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; }
.card { display: flex; flex-direction: column; min-height: 238px; padding: 20px; border: 1px solid var(--line); background: var(--surface); box-shadow: var(--shadow); }
.card:hover { border-color: color-mix(in srgb, var(--accent) 60%, var(--line)); }
.card-top { display: flex; justify-content: space-between; gap: 16px; align-items: start; }
.repo { font: 700 17px/1.35 ui-monospace, SFMono-Regular, Consolas, monospace; overflow-wrap: anywhere; }
.badge { border: 1px solid var(--line); padding: 2px 8px; font: 700 12px/1.6 ui-monospace, SFMono-Regular, Consolas, monospace; white-space: nowrap; }
.badge.daily { color: var(--daily); border-color: color-mix(in srgb, var(--daily) 45%, var(--line)); }
.badge.weekly { color: var(--weekly); border-color: color-mix(in srgb, var(--weekly) 45%, var(--line)); }
.badge.monthly { color: var(--monthly); border-color: color-mix(in srgb, var(--monthly) 45%, var(--line)); }
.summary { color: var(--muted); margin: 18px 0; flex: 1; }
.scoreline { display: flex; flex-wrap: wrap; gap: 9px 13px; font: 600 12px/1.5 ui-monospace, SFMono-Regular, Consolas, monospace; font-variant-numeric: tabular-nums; }
.scoreline span { color: var(--muted); }
.scoreline strong { color: var(--ink); }
.card-link { margin-top: 18px; font-weight: 650; }
.history { padding: 0; list-style: none; border-top: 1px solid var(--line); }
.history li { display: flex; justify-content: space-between; gap: 16px; padding: 13px 0; border-bottom: 1px solid var(--line); }
.history span { color: var(--muted); }
.prose h1 { font-size: clamp(31px, 5vw, 48px); overflow-wrap: anywhere; }
.prose h2 { border-top: 1px solid var(--line); padding-top: 30px; margin-top: 42px; }
.prose p, .prose li { font-size: 16px; }
.prose ul { padding-left: 1.25em; }
.prose li + li { margin-top: 7px; }
.prose table { width: 100%; border-collapse: collapse; margin: 18px 0 28px; font-variant-numeric: tabular-nums; }
.prose th, .prose td { padding: 10px 12px; border-bottom: 1px solid var(--line); text-align: left; }
.prose th { color: var(--muted); font-size: 13px; }
.prose code { background: var(--code); padding: 2px 5px; font-family: ui-monospace, SFMono-Regular, Consolas, monospace; font-size: .92em; }
.prose pre { overflow-x: auto; background: var(--code); padding: 16px; border: 1px solid var(--line); }
.prose pre code { padding: 0; background: transparent; }
.prose img { display: block; max-width: 100%; height: auto; margin: 18px auto; }
.prose p[align="center"], .prose h1[align="center"], .prose h2[align="center"], .prose div[align="center"] { text-align: center; }
.prose p[align="center"] img, .prose a > img, .prose picture img { display: inline-block; margin: 8px 4px; }
.prose picture { display: inline-block; max-width: 100%; }
.prose video { display: block; width: 100%; max-width: 100%; margin: 22px auto; background: #101214; }
.prose hr { border: 0; border-top: 1px solid var(--line); margin: 42px 0; }
.prose blockquote { margin: 20px 0; padding: 2px 0 2px 18px; border-left: 3px solid var(--accent); color: var(--muted); }
.prose details { margin: 20px 0; padding: 12px 16px; border: 1px solid var(--line); background: var(--surface); }
.prose summary { cursor: pointer; font-weight: 700; color: var(--ink); }
.prose table { display: block; overflow-x: auto; }
.prose td { vertical-align: top; }
.localized-readme { margin-top: 72px; padding-top: 40px; border-top: 2px solid var(--ink); }
.localized-readme-head { margin-bottom: 30px; }
.localized-readme-head h2 { margin: 0 0 8px; padding: 0; border: 0; }
.localized-readme-head p { margin: 0; color: var(--muted); font-size: 14px; }
.localized-readme-body > h1:first-child { margin-top: 0; }
.back { display: inline-block; margin-bottom: 28px; color: var(--muted); }
.footer { border-top: 1px solid var(--line); padding: 24px 0 42px; color: var(--muted); font-size: 13px; }
.empty { color: var(--muted); border: 1px dashed var(--line); padding: 24px; }
@media (max-width: 760px) {
  .shell { width: min(100% - 32px, 1120px); }
  main { padding-top: 36px; }
  .nav { align-items: flex-start; flex-direction: column; padding: 14px 0; }
  .stats { grid-template-columns: repeat(2, 1fr); }
  .stat:nth-child(2) { border-right: 0; }
  .stat:nth-child(-n+2) { border-bottom: 1px solid var(--line); }
  .grid { grid-template-columns: 1fr; }
  .section-head { align-items: start; flex-direction: column; }
}
"""


def inline(text: str) -> str:
    escaped = html.escape(text, quote=False)
    escaped = re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", lambda m: f'<img src="{html.escape(m.group(2), quote=True)}" alt="{html.escape(m.group(1), quote=True)}">', escaped)
    escaped = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", lambda m: f'<a href="{html.escape(m.group(2), quote=True)}">{m.group(1)}</a>', escaped)
    escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", escaped)
    return escaped


def render_markdown(text: str) -> str:
    # Python-Markdown deliberately leaves Markdown inside raw HTML containers
    # untouched unless md_in_html is enabled per container. Official READMEs
    # commonly put tables, lists, and fenced examples inside <details> blocks.
    text = re.sub(
        r"<details(?![^>]*\bmarkdown\s*=)([^>]*)>",
        r'<details markdown="1"\1>',
        text,
        flags=re.I,
    )
    rendered = markdown_lib.markdown(
        text,
        extensions=["extra", "sane_lists", "toc"],
        extension_configs={"toc": {"slugify": slugify_unicode, "permalink": False}},
        output_format="html5",
    )
    soup = BeautifulSoup(rendered, "html.parser")
    for unsafe in soup.find_all(["script", "style", "iframe", "object", "embed", "form"]):
        unsafe.decompose()
    cleaned = bleach.clean(
        str(soup),
        tags={
            "a", "blockquote", "br", "code", "del", "details", "div", "em", "h1", "h2", "h3", "h4", "h5", "h6",
            "hr", "img", "kbd", "li", "ol", "p", "picture", "pre", "source", "span", "strong", "sub", "summary",
            "sup", "table", "tbody", "td", "th", "thead", "tr", "ul", "video",
        },
        attributes={
            "*": ["id", "class", "align", "title"],
            "a": ["href", "target", "rel"],
            "img": ["src", "srcset", "alt", "width", "height", "loading"],
            "source": ["src", "srcset", "media", "type"],
            "video": ["src", "width", "height", "controls", "poster", "preload"],
            "details": ["open"],
            "td": ["width", "align", "colspan", "rowspan"],
            "th": ["width", "align", "colspan", "rowspan"],
            "table": ["align"],
        },
        protocols={"http", "https", "mailto"},
        strip=True,
    )
    soup = BeautifulSoup(cleaned, "html.parser")
    heading_by_text = {
        heading.get_text(" ", strip=True): heading.get("id")
        for heading in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"])
        if heading.get("id")
    }
    known_ids = {value for value in heading_by_text.values() if value}
    for link in soup.find_all("a", href=True):
        href = link["href"]
        if href.startswith("#") and href[1:] not in known_ids:
            matching = heading_by_text.get(link.get_text(" ", strip=True))
            if matching:
                link["href"] = f"#{matching}"
        elif href.startswith(("http://", "https://")):
            link["target"] = "_blank"
            link["rel"] = "noopener noreferrer"
    for image in soup.find_all("img"):
        image["loading"] = "lazy"
    for video in soup.find_all("video"):
        video["preload"] = "metadata"
    return str(soup)


def section(text: str, heading: str) -> str:
    match = re.search(rf"^## {re.escape(heading)}\s*$\n(.*?)(?=^## |\Z)", text, re.M | re.S)
    return match.group(1).strip() if match else ""


def first_paragraph(text: str) -> str:
    return text.split("\n\n", 1)[0].strip()


def page(title: str, body: str, latest_date: str | None, prefix: str = "") -> str:
    latest_link = f'<a href="{prefix}daily/{latest_date}.html">最新日报</a>' if latest_date else ""
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="color-scheme" content="light dark">
  <title>{html.escape(title)}</title>
  <link rel="stylesheet" href="{prefix}style.css">
</head>
<body>
  <header class="topbar"><nav class="shell nav">
    <a class="brand" href="{prefix}index.html">GitHub Trending</a>
    <div class="navlinks"><a href="{prefix}index.html">首页</a>{latest_link}<a href="{prefix}../index.md">Markdown Wiki</a><a href="https://github.com/trending?since=weekly">数据源</a></div>
  </nav></header>
  {body}
  <footer class="footer"><div class="shell">本地静态知识站 · Markdown Wiki同步生成 · 候选来自GitHub Trending</div></footer>
</body></html>"""


def card(entry: dict, one_line: str, link: str, period: str) -> str:
    label = PERIOD_LABELS[period]
    return f"""<article class="card">
  <div class="card-top"><h3 class="repo">{html.escape(entry['full_name'])}</h3><span class="badge {period}">{label}</span></div>
  <p class="summary">{html.escape(one_line)}</p>
  <div class="scoreline"><strong>等级 {entry['grade']}</strong><span>T {entry['trend_score']}</span><span>Q {entry['quality_score']}</span><span>V {entry['value_score']}</span><span>F {entry['final_score']}</span></div>
  <a class="card-link" href="{html.escape(link, quote=True)}">查看详细介绍 →</a>
</article>"""


def normalized_entry(item: dict) -> dict:
    value = evaluation_value(item)
    return {
        "full_name": item["full_name"],
        "grade": item["final"]["grade"],
        "trend_score": item["trend"]["score"],
        "quality_score": item["quality"]["total"],
        "value_score": value["total"],
        "final_score": item["final"]["score"],
    }


def period_sections(featured: dict[str, list[dict]], one_line: dict[str, str], link_prefix: str) -> str:
    groups = []
    notes = {"daily": "短期突然升温", "weekly": "一周持续增长", "monthly": "月度稳定关注"}
    for period in PERIOD_ORDER:
        items = []
        for item in featured[period]:
            name = item["full_name"]
            items.append(
                card(
                    normalized_entry(item),
                    one_line[name],
                    f"{link_prefix}{name.replace('/', '__')}.html",
                    period,
                )
            )
        groups.append(
            f'<section><div class="section-head"><h2>{PERIOD_LABELS[period]}精选</h2><p>{notes[period]}</p></div>'
            f'<div class="grid">{"".join(items) or "<div class=empty>暂无新增项目</div>"}</div></section>'
        )
    return "".join(groups)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    site = root / "site"
    (site / "daily").mkdir(parents=True, exist_ok=True)
    (site / "repos").mkdir(parents=True, exist_ok=True)
    for generated_dir in (site / "daily", site / "repos"):
        for generated_file in generated_dir.glob("*.html"):
            generated_file.unlink()
    (site / "style.css").write_text(STYLE.strip() + "\n", encoding="utf-8")

    catalog = json.loads((root / "catalog.json").read_text(encoding="utf-8"))
    readme_manifest_path = root / "readmes" / "manifest.json"
    readme_entries = {}
    if readme_manifest_path.is_file():
        readme_manifest = json.loads(readme_manifest_path.read_text(encoding="utf-8-sig"))
        readme_entries = {entry["full_name"]: entry for entry in readme_manifest.get("entries", [])}
    daily_files = sorted((root / "daily").glob("*.md"), reverse=True)
    latest_date = daily_files[0].stem if daily_files else None
    md_by_name = {}
    one_line = {}
    for entry in catalog["entries"]:
        name = entry["full_name"]
        md_path = root / entry["card"]
        text = md_path.read_text(encoding="utf-8")
        localized_html = ""
        if name in readme_entries:
            readme_entry = readme_entries[name]
            readme_path = root / readme_entry["translation"]
            _, readme_body = split_translation(readme_path.read_text(encoding="utf-8-sig"))
            readme_body = absolutize_markdown_links(
                readme_body,
                name,
                readme_entry["source_branch"],
                readme_entry["source_path"],
            )
            localized_html = (
                '<section class="localized-readme" id="chinese-readme">'
                '<div class="localized-readme-head"><h2>中文 README</h2>'
                f'<p>官方 README 的中文直译 · <a href="{html.escape(readme_entry["source_url"], quote=True)}">查看原文</a></p></div>'
                f'<div class="localized-readme-body">{render_markdown(readme_body)}</div></section>'
            )
        md_by_name[name] = text
        one_line[name] = first_paragraph(section(text, "一句话介绍"))
        back_href = f"../daily/{latest_date}.html" if latest_date else "../index.html"
        back_label = "返回最新日报" if latest_date else "返回首页"
        detail_body = f'<main><article class="reading prose"><a class="back" href="{back_href}">← {back_label}</a>{render_markdown(text)}{localized_html}</article></main>'
        (site / "repos" / f"{name.replace('/', '__')}.html").write_text(page(name, detail_body, latest_date, "../"), encoding="utf-8")

    latest_stats_html = '<div class="stats">' + "".join(
        f'<div class="stat"><strong>0</strong><span>{label}</span></div>'
        for label in ("Trending页面", "去重候选", "通过筛选", "新增展示")
    ) + "</div>"
    latest_period_sections = period_sections({period: [] for period in PERIOD_ORDER}, one_line, "repos/")
    for daily_path in daily_files:
        report_date = daily_path.stem
        incoming = json.loads((root / f"incoming/{report_date}.json").read_text(encoding="utf-8"))
        evaluation = json.loads((root / f"evaluations/{report_date}.json").read_text(encoding="utf-8"))
        accepted_eval = [item for item in evaluation["entries"] if item["final"]["status"] == "accepted"]
        featured = select_period_features(evaluation["entries"], catalog, date.fromisoformat(report_date))
        new_count = sum(len(items) for items in featured.values())
        pool = incoming.get("candidate_pool") or incoming.get("topic_filter") or {}
        stats = [
            (str(len(incoming["pages"])), "Trending页面"),
            (str(pool.get("raw_candidate_count", len(evaluation["entries"]))), "去重候选"),
            (str(len(accepted_eval)), "通过筛选"),
            (str(new_count), "新增展示"),
        ]
        stats_html = "<div class=\"stats\">" + "".join(f'<div class="stat"><strong>{value}</strong><span>{label}</span></div>' for value, label in stats) + "</div>"
        if report_date == latest_date:
            latest_stats_html = stats_html
            latest_period_sections = period_sections(featured, one_line, "repos/")
        groups = period_sections(featured, one_line, "../repos/")
        daily_body = f"""<main><div class="shell">
          <div class="eyebrow">Daily Brief · {report_date}</div>
          <h1>GitHub Trending 项目日报</h1>
          <p class="lede">从完整Trending页面中筛出值得进一步了解的项目；同一仓库只收录一次，并按最强趋势归入日榜、周榜或月榜。</p>
          {stats_html}{groups}
        </div></main>"""
        (site / "daily" / f"{report_date}.html").write_text(page(f"GitHub Trending 项目日报｜{report_date}", daily_body, latest_date, "../"), encoding="utf-8")

    history = "".join(f'<li><a href="daily/{path.stem}.html">{path.stem}</a><span>查看日报</span></li>' for path in daily_files)
    if not history:
        history = '<li><span>尚未生成日报</span><span>等待首次采集</span></li>'
    home_body = f"""<main><div class="shell">
      <div class="eyebrow">Local Knowledge Base</div>
      <h1>GitHub Trending 项目知识库</h1>
      <p class="lede">每天从GitHub Trending发现正在获得关注的项目，不做主题预筛选；同一仓库只收录一次，并分别呈现日榜、周榜和月榜。</p>
      {latest_stats_html}
      {latest_period_sections}
      <section><div class="section-head"><h2>历史日报</h2><p>按日期倒序</p></div><ul class="history">{history}</ul></section>
    </div></main>"""
    (site / "index.html").write_text(page("GitHub Trending 项目知识库", home_body, latest_date), encoding="utf-8")
    print(f"SITE PASS project_pages={len(catalog['entries'])} daily_pages={len(daily_files)}")


if __name__ == "__main__":
    main()
