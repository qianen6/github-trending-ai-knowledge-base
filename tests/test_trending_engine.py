from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path


ENGINE = Path(__file__).parents[1] / "scripts" / "trending_engine.py"
SPEC = importlib.util.spec_from_file_location("trending_engine", ENGINE)
assert SPEC and SPEC.loader
engine = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(engine)


def score_blocks() -> tuple[dict, dict]:
    evidence = ["https://github.com/example/new-hot/blob/main/README.md"]
    quality = {
        "scores": {
            "readme_source_consistency": 16,
            "implementation_completeness": 16,
            "install_usage_clarity": 12,
            "tests_ci_release": 15,
            "docs_examples_errors": 8,
            "architecture_maintenance": 8,
            "dependency_transparency": 4,
        },
        "total": 79,
        "rationale": "Static source, tests, documentation and release evidence are present.",
        "evidence_urls": evidence,
    }
    value = {
        "scores": {
            "problem_value": 16,
            "practical_improvement": 16,
            "use_frequency": 12,
            "workflow_completeness": 12,
            "interoperability": 8,
            "extensibility": 8,
            "compounding_value": 4,
            "cost_benefit": 4,
        },
        "total": 80,
        "level": "P3",
        "rationale": "The project supports a complete and reusable production workflow.",
        "evidence_urls": evidence,
    }
    return quality, value


def repo(full_name: str, created_at: str) -> dict:
    quality, value = score_blocks()
    url = f"https://github.com/{full_name}"
    evidence = [url, url + "/blob/main/README.md", url + "/blob/main/src/main.py"]
    quality["evidence_urls"] = evidence
    value["evidence_urls"] = evidence
    return {
        "full_name": full_name,
        "url": url,
        "description": "Useful developer workflow",
        "category": "Developer Tool",
        "created_at": created_at,
        "pushed_at": "2026-08-27T00:00:00Z",
        "is_fork": False,
        "is_mirror": False,
        "archived": False,
        "language": "Python",
        "hard_filter": {key: True for key in engine.COMMON_HARD_GATES},
        "license": {
            "name": "MIT",
            "scope_zh": "适用于仓库源代码，允许使用、修改、分发和商业使用，但需保留版权与许可证声明。",
            "evidence_urls": [url + "/blob/main/LICENSE"],
        },
        "quality": quality,
        "value": value,
        "card": {
            "one_line": "One-line introduction.",
            "what": "What the project does.",
            "audience": ["Developers"],
            "usage": "Describe a task and receive an output.",
            "features": ["Reusable workflow"],
            "why": "It is receiving attention.",
            "strengths": ["Complete implementation"],
            "limitations": ["Static review only"],
            "value": "A reusable project workflow.",
        },
        "evidence_urls": evidence,
    }


def pages() -> list[dict]:
    result = []
    periods = {"daily": (100, 10), "weekly": (500, 50), "monthly": (900, 90)}
    for scope in sorted(engine.VALID_SCOPES):
        for period in sorted(engine.VALID_PERIODS):
            first, second = periods[period]
            language_path = "" if scope == "global" else f"/{scope}"
            result.append(
                {
                    "scope": scope,
                    "period": period,
                    "spoken_language": "any",
                    "source_url": f"https://github.com/trending{language_path}?since={period}",
                    "captured_at": "2026-08-27T09:00:00+08:00",
                    "raw_sha256": "a" * 64,
                    "status": "success",
                    "entries": [
                        {
                            "rank": 1,
                            "full_name": "example/new-hot",
                            "url": "https://github.com/example/new-hot",
                            "description": "New system",
                            "primary_language": "Python",
                            "total_stars": 1000,
                            "total_forks": 100,
                            "period_stars": first,
                            "built_by": ["alice"],
                        },
                        {
                            "rank": 2,
                            "full_name": "example/revived-hot",
                            "url": "https://github.com/example/revived-hot",
                            "description": "Revived system",
                            "primary_language": "Python",
                            "total_stars": 5000,
                            "total_forks": 500,
                            "period_stars": second,
                            "built_by": ["bob"],
                        },
                    ],
                }
            )
    return result


def evaluation(name: str, period: str, score: int, first_accepted: str = "2026-08-28") -> tuple[dict, dict]:
    components = {
        "daily_percentile": 10.0,
        "weekly_percentile": 10.0,
        "monthly_percentile": 10.0,
        "rank_momentum": 50.0,
        "cross_period": 100.0,
    }
    components[f"{period}_percentile"] = 100.0
    item = {
        "full_name": name,
        "hot_type": "REVIVED_HOT",
        "trend": {
            "components": components,
            "periods_present": ["daily", "weekly", "monthly"],
            "period_stars": {"daily": 10, "weekly": 20, "monthly": 30},
        },
        "quality": {"total": 80},
        "value": {"total": 80, "level": "P3"},
        "final": {"status": "accepted", "score": score},
        "card": {"one_line": "Project"},
    }
    catalog_entry = {"full_name": name, "first_accepted": first_accepted}
    return item, catalog_entry


class TrendingEngineTests(unittest.TestCase):
    def test_period_features_are_capped_deduped_and_new_only(self) -> None:
        evaluations = []
        catalog_entries = []
        score = 100
        for period in engine.PERIOD_ORDER:
            for index in range(7):
                item, catalog_entry = evaluation(f"example/{period}-{index}", period, score)
                evaluations.append(item)
                catalog_entries.append(catalog_entry)
                score -= 1
        old, old_catalog = evaluation("example/already-collected", "daily", 101, "2026-08-27")
        evaluations.append(old)
        catalog_entries.append(old_catalog)
        groups = engine.select_period_features(
            evaluations,
            {"entries": catalog_entries},
            date.fromisoformat("2026-08-28"),
        )
        self.assertEqual({period: len(items) for period, items in groups.items()}, {"daily": 5, "weekly": 5, "monthly": 5})
        names = [item["full_name"] for items in groups.values() for item in items]
        self.assertEqual(len(names), len(set(names)))
        self.assertNotIn("example/already-collected", names)

    def test_trending_scores_are_immediate_and_hot_types_are_retained(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name in ("README.md", "WORKFLOW.md", "SCREENING_RULES.md", "index.md"):
                (root / name).write_text("test\n", encoding="utf-8")
            (root / "catalog.json").write_text(
                json.dumps({"schema_version": 3, "updated_at": "2026-08-27", "entries": []}), encoding="utf-8"
            )
            payload = {
                "schema_version": 4,
                "capture_date": "2026-08-27",
                "captured_at": "2026-08-27T09:00:00+08:00",
                "candidate_pool": {
                    "description": "All deduplicated Trending repositories; no topic filter.",
                    "dedupe_key": "full_name",
                    "raw_candidate_count": 2,
                    "evaluated_candidate_count": 2,
                },
                "pages": pages(),
                "repositories": [
                    repo("example/new-hot", "2026-08-01T00:00:00Z"),
                    repo("example/revived-hot", "2020-01-01T00:00:00Z"),
                ],
            }
            incoming = root / "incoming.json"
            incoming.write_text(json.dumps(payload), encoding="utf-8")
            summary = engine.ingest(root, incoming)
            self.assertEqual(summary["candidates"], 2)
            self.assertEqual(summary["newly_accepted"], summary["accepted"])
            entries = json.loads((root / "evaluations/2026-08-27.json").read_text(encoding="utf-8"))["entries"]
            by_name = {entry["full_name"]: entry for entry in entries}
            self.assertEqual(by_name["example/new-hot"]["hot_type"], "NEW_HOT")
            self.assertEqual(by_name["example/revived-hot"]["hot_type"], "REVIVED_HOT")
            self.assertEqual(by_name["example/revived-hot"]["hard_filter"]["status"], "PASS")
            self.assertEqual(by_name["example/revived-hot"]["license"]["name"], "MIT")
            self.assertNotIn("engineering", by_name["example/revived-hot"]["hard_filter"])
            self.assertIn("value", by_name["example/revived-hot"])

    def test_every_deduplicated_trending_repo_must_be_evaluated(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            payload = {
                "schema_version": 4,
                "capture_date": "2026-08-27",
                "captured_at": "2026-08-27T09:00:00+08:00",
                "candidate_pool": {
                    "description": "No topic filter.",
                    "dedupe_key": "full_name",
                    "raw_candidate_count": 2,
                    "evaluated_candidate_count": 1,
                },
                "pages": pages(),
                "repositories": [repo("example/new-hot", "2026-08-01T00:00:00Z")],
            }
            incoming = root / "incoming.json"
            incoming.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(ValueError):
                engine.ingest(root, incoming)

    def test_exact_page_matrix_is_required(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            payload = {
                "schema_version": 4,
                "capture_date": "2026-08-27",
                "captured_at": "2026-08-27T09:00:00+08:00",
                "candidate_pool": {
                    "description": "No topic filter.",
                    "dedupe_key": "full_name",
                    "raw_candidate_count": 2,
                    "evaluated_candidate_count": 2,
                },
                "pages": pages()[:-1],
                "repositories": [
                    repo("example/new-hot", "2026-08-01T00:00:00Z"),
                    repo("example/revived-hot", "2020-01-01T00:00:00Z"),
                ],
            }
            incoming = root / "incoming.json"
            incoming.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(ValueError):
                engine.ingest(root, incoming)

    def test_page_one_hundred_limit_cannot_hide_duplicate_ranks(self) -> None:
        page = pages()[0]
        page["entries"][1]["rank"] = 1
        with self.assertRaises(ValueError):
            engine.validate_page(page, "2026-08-27")

    def test_score_component_bounds_are_enforced(self) -> None:
        candidate = repo("example/new-hot", "2026-08-01T00:00:00Z")
        candidate["value"]["scores"]["cost_benefit"] = 6
        with self.assertRaises(ValueError):
            engine.validate_repository(candidate)

    def test_license_scope_is_chinese_description_not_a_gate(self) -> None:
        candidate = repo("example/new-hot", "2026-08-01T00:00:00Z")
        candidate["license"] = {
            "name": "未声明",
            "scope_zh": "仓库没有声明统一许可证，因此这里只记录其公开可见范围，不据此改变项目评分。",
            "evidence_urls": [],
        }
        engine.validate_repository(candidate)
        trend = {
            "score": 80.0,
            "pass": True,
            "components": {
                "daily_percentile": 80.0,
                "weekly_percentile": 80.0,
                "monthly_percentile": 80.0,
                "rank_momentum": 50.0,
                "cross_period": 100.0,
            },
            "period_stars": {"daily": 100, "weekly": 500, "monthly": 900},
            "appearance_count": 3,
            "periods_present": ["daily", "weekly", "monthly"],
            "average_rank": 1.0,
            "previous_average_rank": None,
        }
        evaluated = engine.evaluate(candidate, trend, date.fromisoformat("2026-08-27"))
        self.assertEqual(evaluated["final"]["status"], "accepted")
        self.assertEqual(evaluated["license"]["name"], "未声明")


if __name__ == "__main__":
    unittest.main()
