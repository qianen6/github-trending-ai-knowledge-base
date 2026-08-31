from __future__ import annotations

from datetime import date
from typing import Any

from .domain import PERIOD_FEATURE_LIMIT, PERIOD_ORDER, SCHEMA_VERSION
from .ranking import primary_period


def select_period_features(
    evaluations: list[dict[str, Any]],
    catalog: dict[str, Any],
    capture_date: date,
    limit: int = PERIOD_FEATURE_LIMIT,
) -> dict[str, list[dict[str, Any]]]:
    """Select new, globally deduplicated projects for all three boards."""
    first_accepted = {
        entry["full_name"]: entry.get("first_accepted")
        for entry in catalog.get("entries", [])
    }
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


def build_daily_edition(
    capture_date: date,
    pages: list[dict[str, Any]],
    evaluations: list[dict[str, Any]],
    raw_candidate_count: int,
    catalog: dict[str, Any],
) -> dict[str, Any]:
    featured = select_period_features(evaluations, catalog, capture_date)
    accepted = [item for item in evaluations if item["final"]["status"] == "accepted"]
    first_accepted = {
        entry["full_name"]: entry.get("first_accepted")
        for entry in catalog.get("entries", [])
    }
    newly_accepted = [
        item
        for item in accepted
        if first_accepted.get(item["full_name"]) == capture_date.isoformat()
    ]
    groups = {
        period: [item["full_name"] for item in featured[period]]
        for period in PERIOD_ORDER
    }
    displayed = [name for period in PERIOD_ORDER for name in groups[period]]
    return {
        "schema_version": 1,
        "knowledge_base_schema_version": SCHEMA_VERSION,
        "date": capture_date.isoformat(),
        "stats": {
            "pages": len(pages),
            "raw_candidates": raw_candidate_count,
            "evaluated": len(evaluations),
            "accepted": len(accepted),
            "rejected": sum(item["final"]["status"] == "rejected" for item in evaluations),
            "newly_accepted": len(newly_accepted),
            "catalog_entries": catalog.get("entry_count", len(catalog.get("entries", []))),
        },
        "featured": groups,
        "displayed_projects": displayed,
    }


def featured_evaluations(
    edition: dict[str, Any], evaluations: list[dict[str, Any]]
) -> dict[str, list[dict[str, Any]]]:
    by_name = {item["full_name"]: item for item in evaluations}
    output: dict[str, list[dict[str, Any]]] = {}
    for period in PERIOD_ORDER:
        names = edition.get("featured", {}).get(period, [])
        missing = [name for name in names if name not in by_name]
        if missing:
            raise ValueError(f"DailyEdition references missing evaluations: {missing}")
        output[period] = [by_name[name] for name in names]
    return output


def validate_daily_edition(edition: dict[str, Any]) -> None:
    if edition.get("schema_version") != 1:
        raise ValueError("unsupported DailyEdition schema_version")
    featured = edition.get("featured")
    if not isinstance(featured, dict) or set(featured) != set(PERIOD_ORDER):
        raise ValueError("DailyEdition featured periods mismatch")
    names = [name for period in PERIOD_ORDER for name in featured[period]]
    if len(names) != len(set(names)):
        raise ValueError("DailyEdition contains duplicate featured projects")
    if edition.get("displayed_projects") != names:
        raise ValueError("DailyEdition displayed_projects mismatch")
