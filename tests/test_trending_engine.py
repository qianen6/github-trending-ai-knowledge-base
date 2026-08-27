from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
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
            "dependency_transparency": 4
        },
        "total": 79,
        "rationale": "Static source, tests, documentation and release evidence are present.",
        "evidence_urls": evidence
    }
    ai_value = {
        "scores": {
            "problem_value": 16,
            "baseline_improvement": 16,
            "ai_necessity": 12,
            "workflow_completeness": 12,
            "model_substitutability": 8,
            "extensibility": 8,
            "compounding_value": 4,
            "cost_benefit": 4
        },
        "total": 80,
        "level": "L3",
        "rationale": "AI drives a complete and reusable production workflow.",
        "evidence_urls": evidence
    }
    return quality, ai_value


def repo(full_name: str, created_at: str, engineering: bool = True) -> dict:
    quality, ai_value = score_blocks()
    url = f"https://github.com/{full_name}"
    evidence = [url, url + "/blob/main/README.md", url + "/blob/main/src/main.py"]
    quality["evidence_urls"] = evidence
    ai_value["evidence_urls"] = evidence
    return {
        "full_name": full_name,
        "url": url,
        "description": "AI workflow",
        "category": "Agent",
        "created_at": created_at,
        "pushed_at": "2026-08-27T00:00:00Z",
        "is_fork": False,
        "is_mirror": False,
        "archived": False,
        "language": "Python",
        "hard_filter": {key: True for key in engine.COMMON_HARD_GATES},
        "license": {
            "code_license": "MIT" if engineering else "未声明",
            "status": "LOW" if engineering else "HIGH",
            "research_allowed": True,
            "engineering_allowed": engineering,
            "risk_tags": [] if engineering else ["LICENSE_MISSING"],
            "evidence_urls": [url]
        },
        "quality": quality,
        "ai_value": ai_value,
        "card": {
            "one_line": "One-line introduction.",
            "what": "What the project does.",
            "audience": ["Developers"],
            "usage": "Describe a task and receive an output.",
            "features": ["Agent workflow"],
            "why": "It is receiving attention.",
            "strengths": ["Complete implementation"],
            "limitations": ["Static review only"],
            "ai": "A reusable AI workflow."
        },
        "evidence_urls": evidence
    }


def pages() -> list[dict]:
    result = []
    periods = {"daily": (100, 10), "weekly": (500, 50), "monthly": (900, 90)}
    for scope in sorted(engine.VALID_SCOPES):
        for period in sorted(engine.VALID_PERIODS):
            first, second = periods[period]
            result.append(
                {
                    "scope": scope,
                    "period": period,
                    "spoken_language": "any",
                    "source_url": f"https://github.com/trending/{'' if scope == 'global' else scope}?since={period}",
                    "captured_at": "2026-08-27T09:00:00+08:00",
                    "raw_sha256": "a" * 64,
                    "status": "success",
                    "entries": [
                        {
                            "rank": 1,
                            "full_name": "example/new-hot",
                            "url": "https://github.com/example/new-hot",
                            "description": "New AI system",
                            "primary_language": "Python",
                            "total_stars": 1000,
                            "total_forks": 100,
                            "period_stars": first,
                            "built_by": ["alice"]
                        },
                        {
                            "rank": 2,
                            "full_name": "example/revived-hot",
                            "url": "https://github.com/example/revived-hot",
                            "description": "Revived AI system",
                            "primary_language": "Python",
                            "total_stars": 5000,
                            "total_forks": 500,
                            "period_stars": second,
                            "built_by": ["bob"]
                        }
                    ]
                }
            )
    return result


class TrendingEngineTests(unittest.TestCase):
    def test_trending_scores_are_immediate_and_hot_types_are_separate(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name in ("README.md", "WORKFLOW.md", "SCREENING_RULES.md", "index.md"):
                (root / name).write_text("test\n", encoding="utf-8")
            (root / "catalog.json").write_text(
                json.dumps({"schema_version": 2, "updated_at": "2026-08-27", "entries": []}), encoding="utf-8"
            )
            payload = {
                "schema_version": 2,
                "capture_date": "2026-08-27",
                "captured_at": "2026-08-27T09:00:00+08:00",
                "topic_filter": {"description": "AI and developer tools", "raw_candidate_count": 2, "selected_candidate_count": 2},
                "pages": pages(),
                "repositories": [
                    repo("example/new-hot", "2026-08-01T00:00:00Z"),
                    repo("example/revived-hot", "2020-01-01T00:00:00Z", engineering=False)
                ]
            }
            incoming = root / "incoming.json"
            incoming.write_text(json.dumps(payload), encoding="utf-8")
            summary = engine.ingest(root, incoming)
            self.assertEqual(summary["candidates"], 2)
            self.assertGreaterEqual(summary["accepted"], 1)
            evaluation = json.loads((root / "evaluations/2026-08-27.json").read_text(encoding="utf-8"))["entries"]
            by_name = {entry["full_name"]: entry for entry in evaluation}
            self.assertEqual(by_name["example/new-hot"]["hot_type"], "NEW_HOT")
            self.assertEqual(by_name["example/revived-hot"]["hot_type"], "REVIVED_HOT")
            self.assertEqual(by_name["example/revived-hot"]["hard_filter"]["research"], "PASS")
            self.assertEqual(by_name["example/revived-hot"]["hard_filter"]["engineering"], "FAIL")
            self.assertNotIn("CONDITIONAL", json.dumps(evaluation))

    def test_exact_page_matrix_is_required(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            payload = {
                "schema_version": 2,
                "capture_date": "2026-08-27",
                "captured_at": "2026-08-27T09:00:00+08:00",
                "topic_filter": {"description": "AI and developer tools", "raw_candidate_count": 2, "selected_candidate_count": 1},
                "pages": pages()[:-1],
                "repositories": [repo("example/new-hot", "2026-08-01T00:00:00Z")]
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
        candidate["quality"]["scores"]["dependency_transparency"] = 6
        with self.assertRaises(ValueError):
            engine.validate_repository(candidate)


if __name__ == "__main__":
    unittest.main()
