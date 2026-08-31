from __future__ import annotations

import json
import os
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

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


def atomic_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="wb", delete=False, dir=path.parent, prefix=path.name + ".", suffix=".tmp"
    ) as handle:
        handle.write(payload)
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
