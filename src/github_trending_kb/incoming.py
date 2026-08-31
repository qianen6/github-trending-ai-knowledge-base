from __future__ import annotations

import re
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from .domain import (CARD_FIELDS, CARD_FORBIDDEN_PATTERNS, CARD_FORBIDDEN_PHRASES, CARD_LIST_FIELDS, CARD_SCALAR_FIELDS, COMMON_HARD_GATES, QUALITY_LIMITS, VALID_PERIODS, VALID_SCOPES, VALUE_LEVELS, VALUE_LIMITS)
from .io_utils import canonical_url, component_total, integer, parse_datetime


def validate_batch_shape(project_root: Path, payload: dict[str, Any]) -> None:
    """Use the published JSON Schema as the structural source of truth."""
    schema_path = project_root / "schemas" / "incoming.schema.json"
    if not schema_path.is_file():
        schema_path = Path(__file__).resolve().parents[2] / "schemas" / "incoming.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(payload), key=lambda error: list(error.path))
    if errors:
        error = errors[0]
        location = ".".join(str(part) for part in error.absolute_path) or "<root>"
        raise ValueError(f"incoming schema validation failed at {location}: {error.message}")

def has_chinese_explanation(value: str) -> bool:
    """Require Chinese prose while still allowing names such as GIS or Jupyter."""
    if not re.search(r"[\u4e00-\u9fff]", value):
        return False
    # A long untranslated English clause wrapped in a few Chinese words is not
    # a Chinese explanation. Technical names remain allowed between Chinese text.
    return re.search(r"[A-Za-z][A-Za-z0-9 ,.'’\-–—/:()]{60,}", value) is None

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
    for field in CARD_SCALAR_FIELDS:
        if not isinstance(card_data[field], str) or not card_data[field].strip():
            raise ValueError(f"card.{field} must be non-empty text")
        if not has_chinese_explanation(card_data[field]):
            raise ValueError(f"card.{field} must contain a Chinese explanation")
    for field in CARD_LIST_FIELDS:
        if not isinstance(card_data[field], list) or not card_data[field] or not all(isinstance(value, str) and value.strip() for value in card_data[field]):
            raise ValueError(f"card.{field} must be a non-empty text list")
        if any(not has_chinese_explanation(value) for value in card_data[field]):
            raise ValueError(f"card.{field} must contain Chinese explanations")
        if field in {"features", "strengths"} and len(card_data[field]) < 2:
            raise ValueError(f"card.{field} must contain at least two project-specific items")
    for field, forbidden_phrases in CARD_FORBIDDEN_PHRASES.items():
        if any(phrase in value for value in card_data[field] for phrase in forbidden_phrases):
            if field == "features":
                raise ValueError("card.features must describe user-visible project capabilities, not repository audit evidence")
            raise ValueError("card.strengths must describe project advantages, not Trending or repository audit evidence")
    for field, patterns in CARD_FORBIDDEN_PATTERNS.items():
        values = card_data[field] if isinstance(card_data[field], list) else [card_data[field]]
        if any(re.search(pattern, value, re.I) for value in values for pattern in patterns):
            raise ValueError(f"card.{field} contains a generic workflow template")

    all_urls = repo["evidence_urls"] + license_data["evidence_urls"] + quality["evidence_urls"] + value["evidence_urls"]
    if not all_urls or any(not isinstance(url, str) or not url.startswith("https://github.com/") for url in all_urls):
        raise ValueError("all evidence must use GitHub URLs")


def normalized_card_set(values: list[str]) -> tuple[str, ...]:
    return tuple(re.sub(r"\s+", " ", value).strip().casefold() for value in values)


def audit_card_batch(repositories: list[dict[str, Any]]) -> dict[str, Any]:
    invalid_names: set[str] = set()
    issues: list[str] = []
    for repo in repositories:
        name = repo.get("full_name", "<unknown>")
        try:
            validate_repository(repo)
        except (KeyError, TypeError, ValueError) as exc:
            invalid_names.add(name)
            issues.append(f"{name}: {exc}")

    duplicates: dict[str, list[list[str]]] = {}
    for field in ("features", "strengths"):
        by_fingerprint: dict[tuple[str, ...], list[str]] = {}
        for repo in repositories:
            name = repo.get("full_name", "<unknown>")
            values = repo.get("card", {}).get(field)
            if not isinstance(values, list) or not all(isinstance(value, str) for value in values):
                continue
            by_fingerprint.setdefault(normalized_card_set(values), []).append(name)
        repeated = [sorted(names, key=str.casefold) for names in by_fingerprint.values() if len(names) > 1]
        duplicates[field] = sorted(repeated, key=lambda names: (-len(names), [name.casefold() for name in names]))
        for names in duplicates[field]:
            invalid_names.update(names)
            issues.append(f"duplicate card.{field} template reused by {', '.join(names)}")

    return {
        "repositories": len(repositories),
        "invalid_repositories": len(invalid_names),
        "duplicate_feature_sets": len(duplicates["features"]),
        "duplicate_strength_sets": len(duplicates["strengths"]),
        "issues": issues,
    }


def card_audit_summary(audit: dict[str, Any]) -> str:
    return " ".join(
        f"{key}={audit[key]}"
        for key in (
            "repositories", "invalid_repositories",
            "duplicate_feature_sets", "duplicate_strength_sets",
        )
    )


def validate_card_batch(repositories: list[dict[str, Any]]) -> dict[str, Any]:
    audit = audit_card_batch(repositories)
    if audit["invalid_repositories"]:
        first_issue = audit["issues"][0] if audit["issues"] else "unknown card-content error"
        raise ValueError(f"card batch validation failed: {card_audit_summary(audit)} first_issue={first_issue}")
    return audit
