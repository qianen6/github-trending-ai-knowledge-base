#!/usr/bin/env python3
"""Deterministic scoring/output engine for a GitHub Trending based radar.

Discovery and evidence reading happen in the scheduled agent. This script
validates page snapshots and evidence, calculates all trend/final scores,
applies binary gates, deduplicates repositories, and writes the knowledge base.
It never clones, installs, imports, or executes a candidate repository.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 4
TREND_PASS = 40.0
QUALITY_PASS = 60
VALUE_PASS = 60
FINAL_PASS = 65.0
NEW_HOT_DAYS = 90
PERIOD_FEATURE_LIMIT = 5
PERIOD_ORDER = ("daily", "weekly", "monthly")
PERIOD_LABELS = {"daily": "日榜", "weekly": "周榜", "monthly": "月榜"}

PERIOD_WEIGHTS = {"weekly": 50, "daily": 20, "monthly": 15}
RANK_WEIGHT = 10
CROSS_PERIOD_WEIGHT = 5
VALID_PERIODS = set(PERIOD_WEIGHTS)
VALID_SCOPES = {"global", "python", "typescript", "javascript", "jupyter-notebook", "go", "rust"}

COMMON_HARD_GATES = (
    "canonical_original",
    "readme_clear",
    "substantive_artifact",
    "readme_code_consistent",
    "run_path_documented",
    "not_spam_or_coursework",
    "install_scripts_reasonable",
    "dependencies_available",
)

QUALITY_LIMITS = {
    "readme_source_consistency": 20,
    "implementation_completeness": 20,
    "install_usage_clarity": 15,
    "tests_ci_release": 20,
    "docs_examples_errors": 10,
    "architecture_maintenance": 10,
    "dependency_transparency": 5,
}

VALUE_LIMITS = {
    "problem_value": 20,
    "practical_improvement": 20,
    "use_frequency": 15,
    "workflow_completeness": 15,
    "interoperability": 10,
    "extensibility": 10,
    "compounding_value": 5,
    "cost_benefit": 5,
}

VALUE_LEVELS = {"P0", "P1", "P2", "P3", "P4"}

CARD_FIELDS = {
    "one_line", "what", "audience", "usage", "features", "why",
    "strengths", "limitations", "value"
}


def parse_date(value: str) -> date:
    return date.fromisoformat(value[:10])


def parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", newline="\n", delete=False,
        dir=path.parent, prefix=path.name + ".", suffix=".tmp"
    ) as handle:
        handle.write(text)
        tmp = Path(handle.name)
    os.replace(tmp, path)


def atomic_json(path: Path, payload: Any) -> None:
    atomic_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def integer(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a nonnegative integer")
    return value


def component_total(scores: dict[str, Any], limits: dict[str, int], label: str) -> int:
    if set(scores) != set(limits):
        raise ValueError(f"{label} keys mismatch")
    total = 0
    for key, maximum in limits.items():
        value = integer(scores[key], f"{label}.{key}")
        if value > maximum:
            raise ValueError(f"{label}.{key} exceeds {maximum}")
        total += value
    return total


def canonical_url(full_name: str) -> str:
    return f"https://github.com/{full_name}"


def validate_page(page: dict[str, Any], capture_date: str) -> None:
    required = {
        "scope", "period", "spoken_language", "source_url", "captured_at",
        "raw_sha256", "status", "entries"
    }
    if set(page) != required:
        raise ValueError("Trending page keys mismatch")
    if page["scope"] not in VALID_SCOPES or page["period"] not in VALID_PERIODS:
        raise ValueError("invalid Trending scope or period")
    if page["status"] not in {"success", "failed"}:
        raise ValueError("page status must be success or failed")
    parse_datetime(page["captured_at"])
    if not re.fullmatch(r"[A-Fa-f0-9]{64}", page["raw_sha256"]):
        raise ValueError("raw_sha256 must be 64 hex characters")
    if not page["source_url"].startswith("https://github.com/trending"):
        raise ValueError("Trending source URL is not official GitHub")
    if page["status"] == "failed" and page["entries"]:
        raise ValueError("failed page must not contain entries")
    seen_ranks = set()
    for entry in page["entries"]:
        needed = {
            "rank", "full_name", "url", "description", "primary_language",
            "total_stars", "total_forks", "period_stars", "built_by"
        }
        if set(entry) != needed:
            raise ValueError("Trending entry keys mismatch")
        rank = integer(entry["rank"], "entry.rank")
        if rank < 1 or rank in seen_ranks:
            raise ValueError("invalid or duplicate rank")
        seen_ranks.add(rank)
        if entry["url"] != canonical_url(entry["full_name"]):
            raise ValueError("noncanonical entry URL")
        integer(entry["total_stars"], "entry.total_stars")
        integer(entry["total_forks"], "entry.total_forks")
        if entry["period_stars"] is not None:
            integer(entry["period_stars"], "entry.period_stars")
        if not isinstance(entry["built_by"], list):
            raise ValueError("built_by must be an array")


def validate_repository(repo: dict[str, Any]) -> None:
    required = {
        "full_name", "url", "description", "category", "created_at", "pushed_at",
        "is_fork", "is_mirror", "archived", "language", "hard_filter", "license",
        "quality", "value", "card", "evidence_urls"
    }
    if set(repo) != required:
        raise ValueError(f"repository keys mismatch for {repo.get('full_name')}")
    if repo["url"] != canonical_url(repo["full_name"]):
        raise ValueError("noncanonical repository URL")
    parse_datetime(repo["created_at"])
    parse_datetime(repo["pushed_at"])
    if any(not isinstance(repo[field], bool) for field in ("is_fork", "is_mirror", "archived")):
        raise ValueError("repository state fields must be boolean")
    if set(repo["hard_filter"]) != set(COMMON_HARD_GATES):
        raise ValueError("hard_filter keys mismatch")
    if any(not isinstance(repo["hard_filter"][key], bool) for key in COMMON_HARD_GATES):
        raise ValueError("hard_filter values must be boolean")

    license_data = repo["license"]
    if set(license_data) != {"name", "scope_zh", "evidence_urls"}:
        raise ValueError("license keys mismatch")
    if not isinstance(license_data["name"], str) or not license_data["name"].strip():
        raise ValueError("license.name must be non-empty text")
    if not isinstance(license_data["scope_zh"], str) or not re.search(r"[\u4e00-\u9fff]", license_data["scope_zh"]):
        raise ValueError("license.scope_zh must be a Chinese explanation")
    if not isinstance(license_data["evidence_urls"], list):
        raise ValueError("license.evidence_urls must be an array")

    quality = repo["quality"]
    q_total = component_total(quality["scores"], QUALITY_LIMITS, "quality.scores")
    if q_total != quality["total"] or not quality.get("rationale") or not quality.get("evidence_urls"):
        raise ValueError("quality evidence or total invalid")

    value = repo["value"]
    v_total = component_total(value["scores"], VALUE_LIMITS, "value.scores")
    if v_total != value["total"] or value.get("level") not in VALUE_LEVELS:
        raise ValueError("project value level or total invalid")
    if not value.get("rationale") or not value.get("evidence_urls"):
        raise ValueError("project value needs rationale and evidence")

    card_data = repo["card"]
    if set(card_data) != CARD_FIELDS:
        raise ValueError("card fields mismatch")
    for field in ("one_line", "what", "usage", "why", "value"):
        if not isinstance(card_data[field], str) or not card_data[field].strip():
            raise ValueError(f"card.{field} must be non-empty text")
    for field in ("audience", "features", "strengths", "limitations"):
        if not isinstance(card_data[field], list) or not card_data[field] or not all(isinstance(value, str) and value.strip() for value in card_data[field]):
            raise ValueError(f"card.{field} must be a non-empty text list")

    all_urls = repo["evidence_urls"] + license_data["evidence_urls"] + quality["evidence_urls"] + value["evidence_urls"]
    if not all_urls or any(not isinstance(url, str) or not url.startswith("https://github.com/") for url in all_urls):
        raise ValueError("all evidence must use GitHub URLs")


def percentile_map(values: dict[str, int | None]) -> dict[str, float]:
    known = [(name, value) for name, value in values.items() if value is not None]
    result = {name: 50.0 for name in values}
    if len(known) == 1:
        result[known[0][0]] = 50.0
    elif len(known) >= 2:
        raw_values = [value for _, value in known]
        for name, value in known:
            less = sum(other < value for other in raw_values)
            equal = sum(other == value for other in raw_values)
            rank = less + (equal - 1) / 2
            result[name] = 100.0 * rank / (len(raw_values) - 1)
    return result


def consolidate_pages(pages: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    repos: dict[str, dict[str, Any]] = {}
    for page in pages:
        if page["status"] != "success":
            continue
        for entry in page["entries"]:
            name = entry["full_name"]
            item = repos.setdefault(
                name,
                {
                    "full_name": name,
                    "url": entry["url"],
                    "description": entry["description"],
                    "primary_language": entry["primary_language"],
                    "total_stars": entry["total_stars"],
                    "total_forks": entry["total_forks"],
                    "appearances": [],
                },
            )
            item["total_stars"] = max(item["total_stars"], entry["total_stars"])
            item["total_forks"] = max(item["total_forks"], entry["total_forks"])
            item["appearances"].append(
                {
                    "scope": page["scope"],
                    "period": page["period"],
                    "rank": entry["rank"],
                    "period_stars": entry["period_stars"],
                    "source_url": page["source_url"],
                    "raw_sha256": page["raw_sha256"],
                }
            )
    return repos


def average_rank(item: dict[str, Any]) -> float | None:
    ranks = [appearance["rank"] for appearance in item.get("appearances", [])]
    return sum(ranks) / len(ranks) if ranks else None


def previous_snapshot(root: Path, capture_date: date) -> dict[str, Any] | None:
    paths = sorted((root / "trending" / "snapshots").glob("*.json"))
    previous = [path for path in paths if parse_date(path.stem) < capture_date]
    return read_json(previous[-1], {}) if previous else None


def compute_trend(root: Path, capture_date: date, consolidated: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    period_values: dict[str, dict[str, int | None]] = {}
    for period in VALID_PERIODS:
        period_values[period] = {}
        for name, item in consolidated.items():
            values = [a["period_stars"] for a in item["appearances"] if a["period"] == period and a["period_stars"] is not None]
            period_values[period][name] = max(values) if values else None
    percentiles = {period: percentile_map(values) for period, values in period_values.items()}

    previous = previous_snapshot(root, capture_date)
    previous_items = {item["full_name"]: item for item in previous.get("repositories", [])} if previous else {}
    output = {}
    for name, item in consolidated.items():
        current_rank = average_rank(item)
        prior_rank = average_rank(previous_items[name]) if name in previous_items else None
        if current_rank is None or prior_rank is None:
            rank_score = 50.0
        else:
            rank_score = max(0.0, min(100.0, 50.0 + (prior_rank - current_rank) * 5.0))
        periods_present = {appearance["period"] for appearance in item["appearances"]}
        cross_score = 100.0 * len(periods_present) / 3.0
        components = {
            "weekly_percentile": round(percentiles["weekly"][name], 2),
            "daily_percentile": round(percentiles["daily"][name], 2),
            "monthly_percentile": round(percentiles["monthly"][name], 2),
            "rank_momentum": round(rank_score, 2),
            "cross_period": round(cross_score, 2),
        }
        score = (
            components["weekly_percentile"] * 0.50
            + components["daily_percentile"] * 0.20
            + components["monthly_percentile"] * 0.15
            + components["rank_momentum"] * 0.10
            + components["cross_period"] * 0.05
        )
        output[name] = {
            "score": round(score, 2),
            "pass": score >= TREND_PASS,
            "components": components,
            "period_stars": {period: period_values[period][name] for period in sorted(VALID_PERIODS)},
            "appearance_count": len(item["appearances"]),
            "periods_present": sorted(periods_present),
            "average_rank": round(current_rank, 2) if current_rank is not None else None,
            "previous_average_rank": round(prior_rank, 2) if prior_rank is not None else None,
        }
    return output


def hard_filter(repo: dict[str, Any]) -> tuple[bool, list[str]]:
    failures = []
    if repo["is_fork"]:
        failures.append("is_fork")
    if repo["is_mirror"]:
        failures.append("is_mirror")
    if repo["archived"]:
        failures.append("archived")
    for gate in COMMON_HARD_GATES:
        if not repo["hard_filter"][gate]:
            failures.append(gate)
    return not failures, failures


def grade(score: float) -> str | None:
    if score >= 85:
        return "S"
    if score >= 75:
        return "A"
    if score >= FINAL_PASS:
        return "B"
    return None


def evaluation_value(evaluation: dict[str, Any]) -> dict[str, Any]:
    """Return the v3 project-value block, with v2 compatibility for stored history."""
    return evaluation.get("value") or evaluation["ai_value"]


def primary_period(evaluation: dict[str, Any]) -> str:
    """Assign one repository to its strongest observed Trending period."""
    trend = evaluation["trend"]
    present = set(trend.get("periods_present") or PERIOD_ORDER)
    candidates = [period for period in PERIOD_ORDER if period in present]
    if not candidates:
        candidates = list(PERIOD_ORDER)
    components = trend.get("components", {})
    return max(
        candidates,
        key=lambda period: (
            components.get(f"{period}_percentile", 50.0),
            -PERIOD_ORDER.index(period),
        ),
    )


def evaluate(repo: dict[str, Any], trend: dict[str, Any], capture_date: date) -> dict[str, Any]:
    common_pass, failures = hard_filter(repo)
    age_days = (capture_date - parse_datetime(repo["created_at"]).date()).days
    hot_type = "NEW_HOT" if age_days <= NEW_HOT_DAYS else "REVIVED_HOT"

    stage = None
    reasons: list[str] = []
    if not common_pass:
        stage = "hard_filter"
        reasons = failures
    elif not trend["pass"]:
        stage = "trend"
        reasons = [f"trend_score_below_{TREND_PASS:g}"]
    elif repo["quality"]["total"] < QUALITY_PASS:
        stage = "quality"
        reasons = [f"quality_score_below_{QUALITY_PASS}"]
    elif repo["value"]["total"] < VALUE_PASS:
        stage = "value"
        reasons = [f"value_score_below_{VALUE_PASS}"]

    final_score = round(trend["score"] * 0.20 + repo["quality"]["total"] * 0.45 + repo["value"]["total"] * 0.35, 2)
    final_grade = grade(final_score)
    if stage is None and final_grade is None:
        stage = "final"
        reasons = [f"final_score_below_{FINAL_PASS:g}"]

    evidence = sorted(set(repo["evidence_urls"] + repo["license"]["evidence_urls"] + repo["quality"]["evidence_urls"] + repo["value"]["evidence_urls"]))
    return {
        "full_name": repo["full_name"],
        "url": repo["url"],
        "category": repo["category"],
        "hot_type": hot_type,
        "repository_age_days": age_days,
        "hard_filter": {
            "status": "PASS" if common_pass else "FAIL",
            "failures": failures,
        },
        "license": repo["license"],
        "trend": trend,
        "quality": repo["quality"],
        "value": repo["value"],
        "card": repo["card"],
        "final": {
            "score": final_score,
            "grade": final_grade,
            "status": "accepted" if stage is None else "rejected",
            "rejection_stage": stage,
            "rejection_reasons": reasons,
        },
        "evidence_urls": evidence,
    }


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
        for legacy_key in ("ai_value_score", "ai_level", "research_gate", "engineering_gate", "license_risk_tags"):
            entry.pop(legacy_key, None)
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
                value_score = entry.get("value_score", entry.get("ai_value_score", 0))
                lines.append(
                    f"| [{entry['full_name']}]({entry['card']}) | {entry['grade']} | {entry['final_score']} | "
                    f"{entry['trend_score']} | {entry['quality_score']} | {value_score} |"
                )
        lines.append("")
    lines.append("候选范围为 GitHub Trending，不代表 GitHub 全站排名。")
    atomic_text(root / "index.md", "\n".join(lines) + "\n")


def select_period_features(
    evaluations: list[dict[str, Any]],
    catalog: dict[str, Any],
    capture_date: date,
    limit: int = PERIOD_FEATURE_LIMIT,
) -> dict[str, list[dict[str, Any]]]:
    """Select new, globally deduplicated projects for daily/weekly/monthly panels."""
    first_accepted = {entry["full_name"]: entry.get("first_accepted") for entry in catalog.get("entries", [])}
    accepted = sorted(
        [
            item
            for item in evaluations
            if item["final"]["status"] == "accepted"
            and first_accepted.get(item["full_name"]) == capture_date.isoformat()
        ],
        key=lambda item: (-item["final"]["score"], item["full_name"].lower()),
    )
    groups = {period: [] for period in PERIOD_ORDER}
    selected_names: set[str] = set()
    for item in accepted:
        name = item["full_name"]
        if name in selected_names:
            continue
        period = primary_period(item)
        if len(groups[period]) >= limit:
            continue
        groups[period].append(item)
        selected_names.add(name)
    return groups


def render_daily(
    root: Path,
    capture_date: date,
    pages: list[dict[str, Any]],
    evaluations: list[dict[str, Any]],
    raw_candidate_count: int,
    catalog: dict[str, Any],
) -> None:
    accepted = sorted([e for e in evaluations if e["final"]["status"] == "accepted"], key=lambda e: -e["final"]["score"])
    featured = select_period_features(evaluations, catalog, capture_date)
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


def ingest(root: Path, input_path: Path) -> dict[str, Any]:
    payload = read_json(input_path, {})
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported schema_version")
    capture_date = parse_date(payload["capture_date"])
    pages = payload.get("pages", [])
    repositories = payload.get("repositories", [])
    if not pages or not repositories:
        raise ValueError("pages and repositories must not be empty")
    if len(pages) != 21:
        raise ValueError(f"expected 21 Trending pages, got {len(pages)}")
    page_keys = [(page["scope"], page["period"]) for page in pages]
    expected_keys = {(scope, period) for scope in VALID_SCOPES for period in VALID_PERIODS}
    if set(page_keys) != expected_keys or len(page_keys) != len(set(page_keys)):
        raise ValueError("Trending page matrix must contain each scope/period exactly once")
    for page in pages:
        validate_page(page, payload["capture_date"])
    names = [repo["full_name"] for repo in repositories]
    if len(names) != len(set(names)):
        raise ValueError("duplicate repository enrichment")
    for repo in repositories:
        validate_repository(repo)

    consolidated = consolidate_pages(pages)
    candidate_pool = payload.get("candidate_pool")
    if not isinstance(candidate_pool, dict) or not candidate_pool.get("description"):
        raise ValueError("candidate_pool description is required")
    if candidate_pool.get("dedupe_key") != "full_name":
        raise ValueError("candidate_pool dedupe_key must be full_name")
    if candidate_pool.get("raw_candidate_count") != len(consolidated):
        raise ValueError("candidate_pool raw count mismatch")
    if candidate_pool.get("evaluated_candidate_count") != len(names):
        raise ValueError("candidate_pool evaluated count mismatch")
    missing_enrichment = sorted(set(consolidated) - set(names))
    not_in_trending = sorted(set(names) - set(consolidated))
    if missing_enrichment or not_in_trending:
        raise ValueError(
            f"candidate pool must evaluate every deduplicated Trending repository; "
            f"missing={missing_enrichment} extra={not_in_trending}"
        )

    raw_dir = root / "trending" / "raw" / capture_date.isoformat()
    for page in pages:
        atomic_json(raw_dir / f"{page['scope']}-{page['period']}.json", page)
    snapshot = {
        "schema_version": SCHEMA_VERSION,
        "capture_date": capture_date.isoformat(),
        "captured_at": payload["captured_at"],
        "candidate_source": "GitHub Trending",
        "page_count": len(pages),
        "raw_repository_count": len(consolidated),
        "evaluated_repository_count": len(names),
        "candidate_pool": candidate_pool,
        "repositories": sorted(consolidated.values(), key=lambda item: item["full_name"].lower()),
    }
    atomic_json(root / "trending" / "snapshots" / f"{capture_date.isoformat()}.json", snapshot)

    trends = compute_trend(root, capture_date, consolidated)
    repo_by_name = {repo["full_name"]: repo for repo in repositories}
    evaluations = [evaluate(repo_by_name[name], trends[name], capture_date) for name in sorted(repo_by_name)]
    atomic_json(
        root / "evaluations" / f"{capture_date.isoformat()}.json",
        {"schema_version": SCHEMA_VERSION, "date": capture_date.isoformat(), "count": len(evaluations), "entries": evaluations},
    )
    catalog = update_catalog(root, capture_date, evaluations)
    for evaluation in evaluations:
        render_card(root, repo_by_name[evaluation["full_name"]], evaluation, capture_date)
    render_index(root, catalog)
    render_daily(root, capture_date, pages, evaluations, len(consolidated), catalog)
    first_accepted = {entry["full_name"]: entry.get("first_accepted") for entry in catalog.get("entries", [])}
    newly_accepted = sum(
        e["final"]["status"] == "accepted" and first_accepted.get(e["full_name"]) == capture_date.isoformat()
        for e in evaluations
    )
    return {
        "capture_date": capture_date.isoformat(),
        "pages": len(pages),
        "raw_candidates": len(consolidated),
        "candidates": len(evaluations),
        "accepted": sum(e["final"]["status"] == "accepted" for e in evaluations),
        "newly_accepted": newly_accepted,
        "rejected": sum(e["final"]["status"] == "rejected" for e in evaluations),
    }


def validate_root(root: Path) -> dict[str, Any]:
    required = [root / "README.md", root / "WORKFLOW.md", root / "SCREENING_RULES.md", root / "index.md", root / "catalog.json"]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise ValueError(f"missing required files: {missing}")
    catalog = read_json(root / "catalog.json", {})
    names = [entry["full_name"] for entry in catalog.get("entries", [])]
    if len(names) != len(set(names)):
        raise ValueError("duplicate catalog full_name")
    for entry in catalog.get("entries", []):
        if not (root / entry["card"]).is_file():
            raise ValueError(f"missing card: {entry['card']}")
    snapshots = sorted((root / "trending" / "snapshots").glob("*.json"))
    for path in snapshots:
        snapshot = read_json(path, {})
        if snapshot.get("raw_repository_count") != len(snapshot.get("repositories", [])):
            raise ValueError(f"snapshot count mismatch: {path}")
    return {
        "files": sum(1 for path in root.rglob("*") if path.is_file()),
        "catalog_entries": len(names),
        "trending_snapshots": len(snapshots),
        "duplicate_keys": 0,
    }


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="GitHub Trending radar deterministic engine")
    sub = root.add_subparsers(dest="command", required=True)
    ingest_cmd = sub.add_parser("ingest")
    ingest_cmd.add_argument("--root", required=True, type=Path)
    ingest_cmd.add_argument("--input", required=True, type=Path)
    validate_cmd = sub.add_parser("validate")
    validate_cmd.add_argument("--root", required=True, type=Path)
    return root


def main() -> int:
    args = parser().parse_args()
    if args.command == "ingest":
        result = ingest(args.root.resolve(), args.input.resolve())
        print("INGEST PASS " + " ".join(f"{key}={value}" for key, value in result.items()))
    else:
        result = validate_root(args.root.resolve())
        print("VALIDATE PASS " + " ".join(f"{key}={value}" for key, value in result.items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
