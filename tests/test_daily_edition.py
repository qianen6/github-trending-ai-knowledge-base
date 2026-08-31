from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from github_trending_kb.edition import (  # noqa: E402
    build_daily_edition,
    featured_evaluations,
    validate_daily_edition,
)
from github_trending_kb.localization import featured_names  # noqa: E402


def evaluation(name: str, period: str, score: float) -> dict:
    components = {"daily_percentile": 0, "weekly_percentile": 0, "monthly_percentile": 0}
    components[f"{period}_percentile"] = 100
    return {
        "full_name": name,
        "final": {"status": "accepted", "score": score},
        "trend": {"periods_present": [period], "components": components},
    }


class DailyEditionTests(unittest.TestCase):
    def test_structured_edition_is_the_display_source(self) -> None:
        day = date(2026, 8, 31)
        items = [evaluation("example/daily", "daily", 80), evaluation("example/weekly", "weekly", 79)]
        catalog = {
            "entry_count": 2,
            "entries": [
                {"full_name": item["full_name"], "first_accepted": day.isoformat()}
                for item in items
            ],
        }
        edition = build_daily_edition(day, [{}] * 21, items, 2, catalog)
        validate_daily_edition(edition)
        self.assertEqual(edition["displayed_projects"], ["example/daily", "example/weekly"])
        featured = featured_evaluations(edition, items)
        self.assertEqual(featured["daily"][0]["full_name"], "example/daily")

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            data = root / "workspace"
            (data / "daily").mkdir(parents=True)
            (data / ".kb-workspace").write_text("test\n", encoding="utf-8")
            (data / "daily" / "2026-08-31.json").write_text(json.dumps(edition), encoding="utf-8")
            # This heading must not leak into coverage when a structured edition exists.
            (data / "daily" / "2026-08-31.md").write_text("### wrong/from-markdown\n", encoding="utf-8")
            self.assertEqual(featured_names(root), {"example/daily", "example/weekly"})


if __name__ == "__main__":
    unittest.main()
