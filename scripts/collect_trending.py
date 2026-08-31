#!/usr/bin/env python3
"""CLI adapter for deterministic Trending and evidence collection."""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC = PROJECT_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from github_trending_kb.collector import *  # noqa: E402,F401,F403
from github_trending_kb.collector import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
