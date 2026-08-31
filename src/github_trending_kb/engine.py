from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import date
from pathlib import Path
from typing import Any

from .domain import *  # compatibility surface for existing callers
from .edition import (
    build_daily_edition,
    select_period_features,
    validate_daily_edition,
)
from .incoming import (
    audit_card_batch,
    card_audit_summary,
    has_chinese_explanation,
    validate_card_batch,
    validate_batch_shape,
    validate_page,
    validate_repository,
)
from .io_utils import (
    atomic_json,
    atomic_text,
    canonical_url,
    component_total,
    integer,
    parse_date,
    parse_datetime,
    read_json,
)
from .publication import render_card, render_daily, render_index, update_catalog
from .ranking import (
    average_rank,
    compute_trend,
    consolidate_pages,
    evaluate,
    evaluation_value,
    grade,
    hard_filter,
    percentile_map,
    previous_snapshot,
    primary_period,
)
from .transaction import ArtifactTransaction
from .workspace import WorkspaceLayout


def ingest(root: Path, input_path: Path) -> dict[str, Any]:
    layout = WorkspaceLayout.discover(root)
    payload = read_json(input_path, {})
    validate_batch_shape(layout.project_root, payload)
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
    expected_keys = {
        (scope, period) for scope in VALID_SCOPES for period in VALID_PERIODS
    }
    if set(page_keys) != expected_keys or len(page_keys) != len(set(page_keys)):
        raise ValueError("Trending page matrix must contain each scope/period exactly once")
    for page in pages:
        validate_page(page, payload["capture_date"])
    names = [repo["full_name"] for repo in repositories]
    if len(names) != len(set(names)):
        raise ValueError("duplicate repository enrichment")
    validate_card_batch(repositories)

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
            "candidate pool must evaluate every deduplicated Trending repository; "
            f"missing={missing_enrichment} extra={not_in_trending}"
        )

    snapshot = {
        "schema_version": SCHEMA_VERSION,
        "capture_date": capture_date.isoformat(),
        "captured_at": payload["captured_at"],
        "candidate_source": "GitHub Trending",
        "page_count": len(pages),
        "raw_repository_count": len(consolidated),
        "evaluated_repository_count": len(names),
        "candidate_pool": candidate_pool,
        "repositories": sorted(
            consolidated.values(), key=lambda item: item["full_name"].lower()
        ),
    }
    trends = compute_trend(layout.data_root, capture_date, consolidated)
    repo_by_name = {repo["full_name"]: repo for repo in repositories}
    evaluations = [
        evaluate(repo_by_name[name], trends[name], capture_date)
        for name in sorted(repo_by_name)
    ]

    transaction = ArtifactTransaction(layout, capture_date.isoformat())
    for page in pages:
        transaction.stage_json(
            Path("trending/raw")
            / capture_date.isoformat()
            / f"{page['scope']}-{page['period']}.json",
            page,
        )
    transaction.stage_json(
        Path("trending/snapshots") / f"{capture_date.isoformat()}.json", snapshot
    )
    transaction.stage_json(
        Path("evaluations") / f"{capture_date.isoformat()}.json",
        {
            "schema_version": SCHEMA_VERSION,
            "date": capture_date.isoformat(),
            "count": len(evaluations),
            "entries": evaluations,
        },
    )

    # Publication functions write only into the staging implementation. Nothing
    # becomes visible until the transaction promotes the complete tree.
    if layout.catalog.is_file():
        shutil.copy2(layout.catalog, transaction.staging / "catalog.json")
    catalog = update_catalog(transaction.staging, capture_date, evaluations)
    for evaluation in evaluations:
        render_card(
            transaction.staging,
            repo_by_name[evaluation["full_name"]],
            evaluation,
            capture_date,
        )
    render_index(transaction.staging, catalog)
    edition = build_daily_edition(
        capture_date, pages, evaluations, len(consolidated), catalog
    )
    validate_daily_edition(edition)
    transaction.stage_json(
        Path("daily") / f"{capture_date.isoformat()}.json", edition
    )
    render_daily(
        transaction.staging,
        capture_date,
        pages,
        evaluations,
        len(consolidated),
        catalog,
        edition,
    )
    transaction.track_tree()
    commit = transaction.commit()

    stats = edition["stats"]
    return {
        "capture_date": capture_date.isoformat(),
        "pages": stats["pages"],
        "raw_candidates": stats["raw_candidates"],
        "candidates": stats["evaluated"],
        "accepted": stats["accepted"],
        "newly_accepted": stats["newly_accepted"],
        "rejected": stats["rejected"],
        "committed_files": commit["file_count"],
    }


def validate_root(root: Path) -> dict[str, Any]:
    layout = WorkspaceLayout.discover(root)
    required = [
        layout.project_root / "README.md",
        layout.project_root / "WORKFLOW.md",
        layout.project_root / "SCREENING_RULES.md",
        layout.index,
        layout.catalog,
    ]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise ValueError(f"missing required files: {missing}")
    catalog = read_json(layout.catalog, {})
    names = [entry["full_name"] for entry in catalog.get("entries", [])]
    if len(names) != len(set(names)):
        raise ValueError("duplicate catalog full_name")
    for entry in catalog.get("entries", []):
        if not layout.path(entry["card"]).is_file():
            raise ValueError(f"missing card: {entry['card']}")
    snapshots = sorted((layout.trending / "snapshots").glob("*.json"))
    for path in snapshots:
        snapshot = read_json(path, {})
        if snapshot.get("raw_repository_count") != len(
            snapshot.get("repositories", [])
        ):
            raise ValueError(f"snapshot count mismatch: {path}")
    editions = sorted(layout.daily.glob("*.json"))
    for path in editions:
        validate_daily_edition(read_json(path, {}))

    commits = sorted((layout.state_root / "commits").glob("*.json"))
    if commits:
        current = read_json(commits[-1], {})
        for relative, expected_hash in current.get("files", {}).items():
            path = layout.path(relative)
            if not path.is_file():
                raise ValueError(f"committed artifact missing: {relative}")
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
            if actual != expected_hash:
                raise ValueError(f"committed artifact changed: {relative}")
    return {
        "files": sum(1 for path in layout.data_root.rglob("*") if path.is_file()),
        "catalog_entries": len(names),
        "trending_snapshots": len(snapshots),
        "daily_editions": len(editions),
        "duplicate_keys": 0,
    }


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        description="GitHub Trending radar deterministic engine"
    )
    sub = root.add_subparsers(dest="command", required=True)
    ingest_cmd = sub.add_parser("ingest")
    ingest_cmd.add_argument("--root", required=True, type=Path)
    ingest_cmd.add_argument("--input", required=True, type=Path)
    validate_cmd = sub.add_parser("validate")
    validate_cmd.add_argument("--root", required=True, type=Path)
    cards_cmd = sub.add_parser("validate-cards")
    cards_cmd.add_argument("--root", required=True, type=Path)
    cards_cmd.add_argument("--input", required=True, type=Path)
    return root


def main() -> int:
    args = parser().parse_args()
    if args.command == "ingest":
        result = ingest(args.root.resolve(), args.input.resolve())
        print("INGEST PASS " + " ".join(f"{key}={value}" for key, value in result.items()))
    elif args.command == "validate":
        result = validate_root(args.root.resolve())
        print("VALIDATE PASS " + " ".join(f"{key}={value}" for key, value in result.items()))
    else:
        payload = read_json(args.input.resolve(), {})
        audit = audit_card_batch(payload.get("repositories", []))
        status = "PASS" if not audit["invalid_repositories"] else "FAIL"
        print(f"CARD VALIDATE {status} {card_audit_summary(audit)}")
        for issue in audit["issues"][:20]:
            print(f"CARD ISSUE {issue}")
        if audit["invalid_repositories"]:
            return 1
    return 0
