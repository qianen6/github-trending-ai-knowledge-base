from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from .domain import (
    COMMON_HARD_GATES,
    FINAL_PASS,
    NEW_HOT_DAYS,
    PERIOD_ORDER,
    QUALITY_PASS,
    TREND_PASS,
    VALID_PERIODS,
    VALUE_PASS,
)
from .io_utils import parse_date, parse_datetime, read_json


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


def compute_trend(
    root: Path, capture_date: date, consolidated: dict[str, dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    period_values: dict[str, dict[str, int | None]] = {}
    for period in VALID_PERIODS:
        period_values[period] = {}
        for name, item in consolidated.items():
            values = [
                a["period_stars"]
                for a in item["appearances"]
                if a["period"] == period and a["period_stars"] is not None
            ]
            period_values[period][name] = max(values) if values else None
    percentiles = {
        period: percentile_map(values) for period, values in period_values.items()
    }

    previous = previous_snapshot(root, capture_date)
    previous_items = (
        {item["full_name"]: item for item in previous.get("repositories", [])}
        if previous
        else {}
    )
    output = {}
    for name, item in consolidated.items():
        current_rank = average_rank(item)
        prior_rank = (
            average_rank(previous_items[name]) if name in previous_items else None
        )
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
            "period_stars": {
                period: period_values[period][name] for period in sorted(VALID_PERIODS)
            },
            "appearance_count": len(item["appearances"]),
            "periods_present": sorted(periods_present),
            "average_rank": (
                round(current_rank, 2) if current_rank is not None else None
            ),
            "previous_average_rank": (
                round(prior_rank, 2) if prior_rank is not None else None
            ),
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
    return evaluation["value"]


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


def evaluate(
    repo: dict[str, Any], trend: dict[str, Any], capture_date: date
) -> dict[str, Any]:
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

    final_score = round(
        trend["score"] * 0.20
        + repo["quality"]["total"] * 0.45
        + repo["value"]["total"] * 0.35,
        2,
    )
    final_grade = grade(final_score)
    if stage is None and final_grade is None:
        stage = "final"
        reasons = [f"final_score_below_{FINAL_PASS:g}"]

    evidence = sorted(
        set(
            repo["evidence_urls"]
            + repo["license"]["evidence_urls"]
            + repo["quality"]["evidence_urls"]
            + repo["value"]["evidence_urls"]
        )
    )
    return {
        "full_name": repo["full_name"],
        "url": repo["url"],
        "category": repo["category"],
        "language": repo.get("language"),
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
