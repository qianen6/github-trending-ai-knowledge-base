from __future__ import annotations
import html
import hashlib
from bs4 import BeautifulSoup

CATALOG_CSS = """
.catalog-tools {display:grid;grid-template-columns:minmax(180px,2fr) 1fr 1fr auto;gap:12px;padding:20px;border:1px solid var(--line);background:var(--surface);margin:24px 0}
.catalog-tools label {font-size:13px;color:var(--muted)}
.catalog-tools input,.catalog-tools select,.catalog-tools button {display:block;width:100%;min-height:42px;padding:8px 10px;border:1px solid var(--line);background:var(--bg);color:var(--ink);font:inherit;border-radius:0}
.catalog-tools button {align-self:end;cursor:pointer}
.catalog-count,.project-meta {color:var(--muted);font-size:14px}
.catalog-item {min-height:180px}
.catalog-item h2 {font-size:18px;margin:0}
.catalog-item p {margin:12px 0}
.catalog-meta {display:flex;flex-wrap:wrap;gap:8px 18px;font-size:13px;color:var(--muted)}
[hidden] {display:none!important}
.contents {padding:16px 20px;border:1px solid var(--line);background:var(--surface);margin:24px 0}
.contents ul {columns:2;padding-left:20px;margin-bottom:0}
.contents li {break-inside:avoid;font-size:14px!important}
.score-explainer {font-size:14px;color:var(--muted);padding:14px 18px;border-left:3px solid var(--accent)}
a:focus-visible,input:focus-visible,select:focus-visible,button:focus-visible,summary:focus-visible {outline:2px solid var(--accent);outline-offset:3px}
@media(max-width:760px){.catalog-tools{grid-template-columns:1fr 1fr;padding:16px}.catalog-tools label:first-child{grid-column:1/-1}.contents ul{columns:1}}
@media(max-width:420px){.catalog-tools{grid-template-columns:1fr}.catalog-tools label:first-child{grid-column:auto}}
"""

CATALOG_SCRIPT = r"""
(function () {
"use strict";
function matchesProject(project, filters) {
  const tokens = (filters.query || "").normalize("NFKC").toLocaleLowerCase().trim().split(/\s+/).filter(Boolean);
  const text = (project.search || "").normalize("NFKC").toLocaleLowerCase();
  return tokens.every(token => text.includes(token)) &&
    (!filters.category || project.category === filters.category) &&
    (!filters.language || project.language === filters.language);
}
if (typeof module !== "undefined" && module.exports) module.exports = {matchesProject};
if (typeof document === "undefined") return;
const form = document.getElementById("catalog-tools");
if (!form) return;
const query = document.getElementById("catalog-query");
const category = document.getElementById("catalog-category");
const language = document.getElementById("catalog-language");
const count = document.getElementById("catalog-count");
const empty = document.getElementById("catalog-empty");
const items = Array.from(document.querySelectorAll("[data-catalog-item]"));
function update() {
  let visible = 0;
  const filters = {query:query.value, category:category.value, language:language.value};
  items.forEach(item => {
    const keep = matchesProject(item.dataset, filters);
    item.hidden = !keep;
    if (keep) visible++;
  });
  count.textContent = "显示 " + visible + " / " + items.length + " 个项目";
  empty.hidden = visible !== 0;
}
form.addEventListener("submit", event => event.preventDefault());
form.addEventListener("input", update);
form.addEventListener("change", update);
document.getElementById("catalog-clear").addEventListener("click", () => {
  form.reset(); update(); query.focus();
});
update();
}());
"""


def catalog_body(
    entries: list[dict], one_line: dict[str, str], languages: dict[str, str]
) -> str:
    categories = sorted({e.get("category") or "未分类" for e in entries})
    language_names = sorted(
        {
            languages.get(e["full_name"]) or e.get("language") or "未标注"
            for e in entries
        }
    )

    def options(values):
        return '<option value="">全部</option>' + "".join(
            f'<option value="{html.escape(v, quote=True)}">{html.escape(v)}</option>'
            for v in values
        )

    items = []
    for entry in sorted(entries, key=lambda e: e["full_name"].casefold()):
        name = entry["full_name"]
        category = entry.get("category") or "未分类"
        language = languages.get(name) or entry.get("language") or "未标注"
        summary = one_line.get(name) or entry.get("one_line", "")
        search = " ".join([name, summary, category, language])
        items.append(
            f'<article class="card catalog-item" data-catalog-item data-name="{html.escape(name,quote=True)}" data-search="{html.escape(search,quote=True)}" data-category="{html.escape(category,quote=True)}" data-language="{html.escape(language,quote=True)}"><h2 class="repo"><a href="repos/{html.escape(name.replace("/","__"),quote=True)}.html">{html.escape(name)}</a></h2><p>{html.escape(summary)}</p><div class="catalog-meta"><span>{html.escape(category)}</span><span>{html.escape(language)}</span><span>最近评估 {html.escape(str(entry.get("last_evaluated") or "暂无记录"))}</span></div></article>'
        )
    return f"""<main><div class="shell"><div class="eyebrow">Catalog · 长期项目目录</div><h1>全部项目</h1><p class="lede">查找已收录的项目，按关键词、分类和语言缩小范围。每日精选与完整目录独立呈现。</p>
<form id="catalog-tools" class="catalog-tools" role="search"><label for="catalog-query">关键词<input id="catalog-query" type="search" placeholder="项目名、用途或技术关键词" autocomplete="off"></label><label for="catalog-category">分类<select id="catalog-category">{options(categories)}</select></label><label for="catalog-language">语言<select id="catalog-language">{options(language_names)}</select></label><button type="button" id="catalog-clear">清空筛选</button></form>
<p id="catalog-count" class="catalog-count" role="status" aria-live="polite">共 {len(entries)} 个项目</p><noscript><p>全部项目已列出；启用 JavaScript 后可使用筛选。</p></noscript><p id="catalog-empty" class="empty" hidden>没有匹配项目，请调整关键词或清空筛选。</p><div class="grid">{"".join(items)}</div></div></main><script src="catalog.js" defer></script>"""


def detail_navigation(card_html: str, readme_html: str, entry: dict) -> str:
    parts = []
    links = []
    for prefix, raw in [("card", card_html), ("readme", readme_html)]:
        soup = BeautifulSoup(raw, "html.parser")
        identifiers = {}
        for node in soup.find_all(id=True):
            if node["id"] == "chinese-readme":
                continue
            old = node["id"]
            new = f"{prefix}-{old}"
            identifiers[old] = new
            node["id"] = new
        for link in soup.find_all("a", href=True):
            if link["href"].startswith("#") and link["href"][1:] in identifiers:
                link["href"] = "#" + identifiers[link["href"][1:]]
        for heading in soup.find_all("h2", id=True):
            links.append((heading["id"], heading.get_text(" ", strip=True)))
        if prefix == "readme" and raw:
            links.append(("chinese-readme", "中文 README"))
            section = soup.find(id="chinese-readme")
            body = soup.select_one(".localized-readme-body")
            if section is not None and body is not None:
                section["data-rendered-sha256"] = hashlib.sha256(
                    str(body).encode("utf-8")
                ).hexdigest()
        parts.append(str(soup))
    contents = (
        '<details class="contents"><summary>本页目录</summary><nav aria-label="本页目录"><ul>'
        + "".join(
            f'<li><a href="#{html.escape(i,quote=True)}">{html.escape(t)}</a></li>'
            for i, t in links
        )
        + "</ul></nav></details>"
    )
    updated = html.escape(str(entry.get("last_evaluated") or "暂无记录"))
    meta = f'<p class="project-meta">最近评估：{updated} · <a href="https://github.com/{html.escape(entry["full_name"],quote=True)}" target="_blank" rel="noopener noreferrer">官方仓库</a></p>'
    scores = '<p class="score-explainer">评分说明：T 为趋势，Q 为静态质量，V 为项目价值，F 为综合分。F = T × 20% + Q × 45% + V × 35%。评分来自静态证据，不代表已安装运行验证。</p>'
    return meta + contents + scores + "".join(parts)
