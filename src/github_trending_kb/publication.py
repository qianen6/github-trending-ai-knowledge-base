from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from .domain import PERIOD_LABELS, PERIOD_ORDER, SCHEMA_VERSION
from .edition import featured_evaluations, select_period_features
from .io_utils import atomic_json, atomic_text, read_json
from .ranking import evaluation_value, primary_period

def update_catalog(root: Path, capture_date: date, evaluations: list[dict[str, Any]]) -> dict[str, Any]:
    path = root / "catalog.json"
    current = read_json(path, {"schema_version": SCHEMA_VERSION, "entries": []})
    by_name = {entry["full_name"]: entry for entry in current.get("entries", [])}
    for evaluation in evaluations:
        if evaluation["final"]["status"] != "accepted":
            continue
        name = evaluation["full_name"]
        entry = by_name.get(name, {})
        value = evaluation_value(evaluation)
        entry.update(
            {
                "full_name": name,
                "url": evaluation["url"],
                "category": evaluation["category"],
                "hot_type": evaluation["hot_type"],
                "first_accepted": entry.get("first_accepted", capture_date.isoformat()),
                "last_evaluated": capture_date.isoformat(),
                "trend_score": evaluation["trend"]["score"],
                "quality_score": evaluation["quality"]["total"],
                "value_score": value["total"],
                "value_level": value["level"],
                "primary_period": primary_period(evaluation),
                "license_name": evaluation["license"]["name"],
                "license_scope_zh": evaluation["license"]["scope_zh"],
                "final_score": evaluation["final"]["score"],
                "grade": evaluation["final"]["grade"],
                "one_line": evaluation["card"]["one_line"],
                "card": f"repos/{name.replace('/', '__')}.md",
            }
        )
        by_name[name] = entry
    payload = {
        "schema_version": SCHEMA_VERSION,
        "updated_at": capture_date.isoformat(),
        "candidate_source": "GitHub Trending",
        "dedupe_key": "full_name",
        "entry_count": len(by_name),
        "entries": sorted(by_name.values(), key=lambda item: (-item["final_score"], item["full_name"].lower())),
    }
    atomic_json(path, payload)
    return payload


def render_card(root: Path, repo: dict[str, Any], evaluation: dict[str, Any], capture_date: date) -> None:
    if evaluation["final"]["status"] != "accepted":
        return
    periods = evaluation["trend"]["period_stars"]
    card_data = evaluation["card"]
    value = evaluation_value(evaluation)
    value_text = card_data.get("value") or card_data.get("ai", "")
    period = primary_period(evaluation)
    bullets = lambda values: "\n".join(f"- {value}" for value in values)
    show = lambda value: value if value is not None else "未展示"
    text = f"""# {repo['full_name']}

## 一句话介绍

{card_data['one_line']}

## 项目是做什么的

{card_data['what']}

## 适合谁

{bullets(card_data['audience'])}

## 使用方式

{card_data['usage']}

## 主要功能

{bullets(card_data['features'])}

## 为什么值得关注

{card_data['why']}

## 主要优点

{bullets(card_data['strengths'])}

## 明确不足

{bullets(card_data['limitations'])}

## License作用域

**{evaluation['license']['name']}**：{evaluation['license']['scope_zh']}

## 项目价值判断

{value_text}

## Trending表现与综合评分

| 项目 | 数值 |
|---|---:|
| 主榜归属 | {PERIOD_LABELS[period]} |
| 热度类型 | {evaluation['hot_type']} |
| Today Stars | {show(periods['daily'])} |
| Week Stars | {show(periods['weekly'])} |
| Month Stars | {show(periods['monthly'])} |
| 趋势 T | {evaluation['trend']['score']} |
| 质量 Q | {evaluation['quality']['total']} |
| 项目价值 V | {value['total']} |
| 综合 F | {evaluation['final']['score']} |
| 等级 | {evaluation['final']['grade']} |

## 项目链接

[{repo['full_name']}]({repo['url']})

"""
    atomic_text(root / "repos" / f"{repo['full_name'].replace('/', '__')}.md", text)


def render_index(root: Path, catalog: dict[str, Any]) -> None:
    lines = ["# GitHub Trending 项目索引", "", f"最后更新：{catalog['updated_at']}", ""]
    for period in PERIOD_ORDER:
        lines.extend([f"## {PERIOD_LABELS[period]}", ""])
        entries = [entry for entry in catalog["entries"] if entry.get("primary_period", "weekly") == period]
        if not entries:
            lines.append("暂无正式收录。")
        else:
            lines.extend(["| 仓库 | 等级 | F | T | Q | V |", "|---|---:|---:|---:|---:|---:|"])
            for entry in entries:
                value_score = entry["value_score"]
                lines.append(
                    f"| [{entry['full_name']}]({entry['card']}) | {entry['grade']} | {entry['final_score']} | "
                    f"{entry['trend_score']} | {entry['quality_score']} | {value_score} |"
                )
        lines.append("")
    lines.append("候选范围为 GitHub Trending，不代表 GitHub 全站排名。")
    atomic_text(root / "index.md", "\n".join(lines) + "\n")

def render_daily(
    root: Path,
    capture_date: date,
    pages: list[dict[str, Any]],
    evaluations: list[dict[str, Any]],
    raw_candidate_count: int,
    catalog: dict[str, Any],
    edition: dict[str, Any] | None = None,
) -> None:
    accepted = sorted([e for e in evaluations if e["final"]["status"] == "accepted"], key=lambda e: -e["final"]["score"])
    featured = (
        featured_evaluations(edition, evaluations)
        if edition is not None
        else select_period_features(evaluations, catalog, capture_date)
    )
    first_accepted = {entry["full_name"]: entry.get("first_accepted") for entry in catalog.get("entries", [])}
    newly_accepted = [e for e in accepted if first_accepted.get(e["full_name"]) == capture_date.isoformat()]
    rejected = [e for e in evaluations if e["final"]["status"] == "rejected"]
    lines = [
        f"# GitHub Trending 项目日报｜{capture_date.isoformat()}",
        "",
        "## 今日概览",
        "",
        f"- Trending页面：{len(pages)}",
        f"- Trending去重项目：{raw_candidate_count}",
        f"- 评估候选：{len(evaluations)}",
        f"- 通过筛选：{len(accepted)}",
        f"- 新增收录：{len(newly_accepted)}",
        f"- 累计项目：{catalog.get('entry_count', len(catalog.get('entries', [])))}",
        "",
    ]
    for period in PERIOD_ORDER:
        chosen = featured[period]
        lines.extend([f"## {PERIOD_LABELS[period]}精选", ""])
        if not chosen:
            lines.extend(["暂无新增项目。", ""])
        for e in chosen:
            period_stars = e["trend"]["period_stars"][period]
            value = evaluation_value(e)
            lines.extend([
                f"### {e['full_name']}", "", e["card"]["one_line"], "",
                f"`{e['final']['grade']}` · T {e['trend']['score']} · Q {e['quality']['total']} · V {value['total']} · F {e['final']['score']} · {PERIOD_LABELS[period]}Stars {period_stars if period_stars is not None else '未展示'}",
                "", f"[查看详细介绍](../repos/{e['full_name'].replace('/', '__')}.md)", ""
            ])
        lines.append("")
    atomic_text(root / "daily" / f"{capture_date.isoformat()}.md", "\n".join(lines))
    atomic_json(
        root / "rejections" / f"{capture_date.isoformat()}.json",
        {"schema_version": SCHEMA_VERSION, "date": capture_date.isoformat(), "count": len(rejected), "entries": rejected},
    )
