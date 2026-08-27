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
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 2
TREND_PASS = 40.0
QUALITY_PASS = 60
AI_VALUE_PASS = 60
FINAL_PASS = 65.0
NEW_HOT_DAYS = 90
DAILY_FEATURE_LIMIT = 5

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

AI_VALUE_LIMITS = {
    "problem_value": 20,
    "baseline_improvement": 20,
    "ai_necessity": 15,
    "workflow_completeness": 15,
    "model_substitutability": 10,
    "extensibility": 10,
    "compounding_value": 5,
    "cost_benefit": 5,
}

AI_LEVELS = {"L0", "L1", "L2", "L3", "L4"}
LICENSE_RISK_TAGS = {
    "LICENSE_MISSING",
    "LICENSE_UNRECOGNIZED",
    "NONCOMMERCIAL",
    "COPYLEFT",
    "MODEL_LICENSE_RESTRICTED",
    "DATASET_RESTRICTION",
    "OUTPUT_RIGHTS_UNCLEAR",
    "DEPENDENCY_LICENSE_CONFLICT",
    "ASSET_ATTRIBUTION_REQUIRED",
}

CARD_FIELDS = {
    "one_line", "what", "audience", "usage", "features", "why",
    "strengths", "limitations", "ai"
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
        "quality", "ai_value", "card", "evidence_urls"
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
    license_keys = {
        "code_license", "status", "research_allowed", "engineering_allowed",
        "risk_tags", "evidence_urls"
    }
    if set(license_data) != license_keys:
        raise ValueError("license keys mismatch")
    if not isinstance(license_data["research_allowed"], bool) or not isinstance(license_data["engineering_allowed"], bool):
        raise ValueError("license pass fields must be boolean")
    unknown_risks = set(license_data["risk_tags"]) - LICENSE_RISK_TAGS
    if unknown_risks:
        raise ValueError(f"unknown license risk tags: {sorted(unknown_risks)}")

    quality = repo["quality"]
    q_total = component_total(quality["scores"], QUALITY_LIMITS, "quality.scores")
    if q_total != quality["total"] or not quality.get("rationale") or not quality.get("evidence_urls"):
        raise ValueError("quality evidence or total invalid")

    ai_value = repo["ai_value"]
    v_total = component_total(ai_value["scores"], AI_VALUE_LIMITS, "ai_value.scores")
    if v_total != ai_value["total"] or ai_value.get("level") not in AI_LEVELS:
        raise ValueError("AI value level or total invalid")
    if not ai_value.get("rationale") or not ai_value.get("evidence_urls"):
        raise ValueError("AI value needs rationale and evidence")

    card_data = repo["card"]
    if set(card_data) != CARD_FIELDS:
        raise ValueError("card fields mismatch")
    for field in ("one_line", "what", "usage", "why", "ai"):
        if not isinstance(card_data[field], str) or not card_data[field].strip():
            raise ValueError(f"card.{field} must be non-empty text")
    for field in ("audience", "features", "strengths", "limitations"):
        if not isinstance(card_data[field], list) or not card_data[field] or not all(isinstance(value, str) and value.strip() for value in card_data[field]):
            raise ValueError(f"card.{field} must be a non-empty text list")

    all_urls = repo["evidence_urls"] + quality["evidence_urls"] + ai_value["evidence_urls"] + license_data["evidence_urls"]
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


def evaluate(repo: dict[str, Any], trend: dict[str, Any], capture_date: date) -> dict[str, Any]:
    common_pass, failures = hard_filter(repo)
    research_pass = common_pass and repo["license"]["research_allowed"]
    engineering_pass = common_pass and repo["license"]["engineering_allowed"]
    age_days = (capture_date - parse_datetime(repo["created_at"]).date()).days
    hot_type = "NEW_HOT" if age_days <= NEW_HOT_DAYS else "REVIVED_HOT"

    stage = None
    reasons: list[str] = []
    if not research_pass:
        stage = "hard_filter"
        reasons = failures + ([] if repo["license"]["research_allowed"] else ["research_license_not_allowed"])
    elif not trend["pass"]:
        stage = "trend"
        reasons = [f"trend_score_below_{TREND_PASS:g}"]
    elif repo["quality"]["total"] < QUALITY_PASS:
        stage = "quality"
        reasons = [f"quality_score_below_{QUALITY_PASS}"]
    elif repo["ai_value"]["total"] < AI_VALUE_PASS:
        stage = "ai_value"
        reasons = [f"ai_value_score_below_{AI_VALUE_PASS}"]

    final_score = round(trend["score"] * 0.20 + repo["quality"]["total"] * 0.45 + repo["ai_value"]["total"] * 0.35, 2)
    final_grade = grade(final_score)
    if stage is None and final_grade is None:
        stage = "final"
        reasons = [f"final_score_below_{FINAL_PASS:g}"]

    evidence = sorted(set(repo["evidence_urls"] + repo["license"]["evidence_urls"] + repo["quality"]["evidence_urls"] + repo["ai_value"]["evidence_urls"]))
    return {
        "full_name": repo["full_name"],
        "url": repo["url"],
        "category": repo["category"],
        "hot_type": hot_type,
        "repository_age_days": age_days,
        "hard_filter": {
            "research": "PASS" if research_pass else "FAIL",
            "engineering": "PASS" if engineering_pass else "FAIL",
            "failures": failures,
        },
        "license": repo["license"],
        "trend": trend,
        "quality": repo["quality"],
        "ai_value": repo["ai_value"],
        "card": repo["card"],
        "final": {
            "score": final_score,
            "grade": final_grade,
            "status": "accepted" if stage is None else "rejected",
            "engineering_eligible": engineering_pass and stage is None,
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
                "ai_value_score": evaluation["ai_value"]["total"],
                "ai_level": evaluation["ai_value"]["level"],
                "final_score": evaluation["final"]["score"],
                "grade": evaluation["final"]["grade"],
                "research_gate": evaluation["hard_filter"]["research"],
                "engineering_gate": evaluation["hard_filter"]["engineering"],
                "license_risk_tags": evaluation["license"]["risk_tags"],
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

## AI价值判断

{card_data['ai']}

## Trending表现与综合评分

| 项目 | 数值 |
|---|---:|
| 热度类型 | {evaluation['hot_type']} |
| Today Stars | {show(periods['daily'])} |
| Week Stars | {show(periods['weekly'])} |
| Month Stars | {show(periods['monthly'])} |
| 趋势 T | {evaluation['trend']['score']} |
| 质量 Q | {evaluation['quality']['total']} |
| AI价值 V | {evaluation['ai_value']['total']} |
| 综合 F | {evaluation['final']['score']} |
| 等级 | {evaluation['final']['grade']} |

## 项目链接

[{repo['full_name']}]({repo['url']})
"""
    atomic_text(root / "repos" / f"{repo['full_name'].replace('/', '__')}.md", text)


def render_index(root: Path, catalog: dict[str, Any]) -> None:
    lines = ["# GitHub Trending 项目索引", "", f"最后更新：{catalog['updated_at']}", ""]
    for hot_type, title in (("NEW_HOT", "近期新项目"), ("REVIVED_HOT", "老项目重新走红")):
        lines.extend([f"## {title}", ""])
        entries = [entry for entry in catalog["entries"] if entry["hot_type"] == hot_type]
        if not entries:
            lines.append("暂无正式收录。")
        else:
            lines.extend(["| 仓库 | 等级 | F | T | Q | V | 科研 | 工程 |", "|---|---:|---:|---:|---:|---:|---|---|"])
            for entry in entries:
                lines.append(
                    f"| [{entry['full_name']}]({entry['card']}) | {entry['grade']} | {entry['final_score']} | "
                    f"{entry['trend_score']} | {entry['quality_score']} | {entry['ai_value_score']} | "
                    f"{entry['research_gate']} | {entry['engineering_gate']} |"
                )
        lines.append("")
    lines.append("候选范围为 GitHub Trending，不代表 GitHub 全站排名。")
    atomic_text(root / "index.md", "\n".join(lines) + "\n")


def render_daily(root: Path, capture_date: date, pages: list[dict[str, Any]], evaluations: list[dict[str, Any]], raw_candidate_count: int) -> None:
    accepted = sorted([e for e in evaluations if e["final"]["status"] == "accepted"], key=lambda e: -e["final"]["score"])
    rejected = [e for e in evaluations if e["final"]["status"] == "rejected"]
    success_pages = sum(page["status"] == "success" for page in pages)
    lines = [
        f"# GitHub Trending AI日报｜{capture_date.isoformat()}",
        "",
        "## 今日概览",
        "",
        f"- Trending页面：{len(pages)}",
        f"- Trending去重项目：{raw_candidate_count}",
        f"- AI主题候选：{len(evaluations)}",
        f"- 正式收录：{len(accepted)}",
        "",
    ]
    for hot_type, title in (("NEW_HOT", "NEW_HOT｜近期新项目"), ("REVIVED_HOT", "REVIVED_HOT｜重新走红项目")):
        chosen = [e for e in accepted if e["hot_type"] == hot_type]
        lines.extend([f"## {title}", ""])
        for e in chosen:
            week = e["trend"]["period_stars"]["weekly"]
            lines.extend([
                f"### {e['full_name']}", "", e["card"]["one_line"], "",
                f"`{e['final']['grade']}` · T {e['trend']['score']} · Q {e['quality']['total']} · V {e['ai_value']['total']} · F {e['final']['score']} · 周榜Stars {week if week is not None else '未展示'}",
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
    topic_filter = payload.get("topic_filter")
    if not isinstance(topic_filter, dict) or not topic_filter.get("description"):
        raise ValueError("topic_filter description is required")
    not_in_trending = sorted(set(names) - set(consolidated))
    if not_in_trending:
        raise ValueError(f"enriched repositories absent from Trending: {not_in_trending}")

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
        "selected_repository_count": len(names),
        "topic_filter": topic_filter,
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
    render_daily(root, capture_date, pages, evaluations, len(consolidated))
    return {
        "capture_date": capture_date.isoformat(),
        "pages": len(pages),
        "raw_candidates": len(consolidated),
        "candidates": len(evaluations),
        "accepted": sum(e["final"]["status"] == "accepted" for e in evaluations),
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
