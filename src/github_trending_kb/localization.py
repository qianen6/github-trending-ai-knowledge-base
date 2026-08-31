from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .github_markdown import absolutize_markdown_links
from .edition import validate_daily_edition
from .workspace import WorkspaceLayout

FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n", re.S)
REQUIRED_FRONTMATTER = {"full_name", "source_url", "source_sha256", "language", "mode"}

def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def split_translation(text: str) -> tuple[dict[str, str], str]:
    normalized = text.replace("\r\n", "\n")
    match = FRONTMATTER_RE.match(normalized)
    if not match:
        raise ValueError("missing translation frontmatter")
    metadata: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        metadata[key.strip()] = value.strip()
    if set(metadata) != REQUIRED_FRONTMATTER:
        raise ValueError(f"translation frontmatter fields mismatch: {sorted(metadata)}")
    return metadata, normalized[match.end() :].strip()


def chinese_prose_count(text: str) -> int:
    without_fences = re.sub(r"```[\s\S]*?```", "", text)
    without_data = re.sub(r"data:[^\s)\"']+", "", without_fences)
    without_urls = re.sub(r"https?://\S+", "", without_data)
    return len(re.findall(r"[\u4e00-\u9fff]", without_urls))


def validate_translation(path: Path, entry: dict[str, Any]) -> None:
    text = path.read_text(encoding="utf-8-sig")
    metadata, body = split_translation(text)
    if metadata["full_name"] != entry["full_name"]:
        raise ValueError(f"full_name mismatch in {path}")
    if metadata["source_url"] != entry["source_url"]:
        raise ValueError(f"source_url mismatch in {path}")
    if metadata["source_sha256"].lower() != entry["source_sha256"].lower():
        raise ValueError(f"source_sha256 mismatch in {path}")
    if metadata["language"] != "zh-CN":
        raise ValueError(f"language must be zh-CN in {path}")
    if metadata["mode"] not in {"faithful-translation", "source-copy"}:
        raise ValueError(f"invalid localization mode in {path}")
    if not re.search(r"^# .+", body, re.M) or not re.search(r"^## .+", body, re.M):
        raise ValueError(f"translated README needs title and sections: {path}")
    if chinese_prose_count(body) < 80:
        raise ValueError(f"translated README has insufficient Chinese prose: {path}")
    prose_for_language = re.sub(r"```[\s\S]*?```", "", body)
    prose_for_language = "\n".join(
        line for line in prose_for_language.splitlines()
        if not line.lstrip().startswith(("|", ">"))
    )
    prose_for_language = re.sub(r"`[^`]+`", "", prose_for_language)
    prose_for_language = re.sub(r"data:[^\s)\"']+", "", prose_for_language)
    prose_for_language = re.sub(r"https?://\S+", "", prose_for_language)
    prose_for_language = re.sub(r"\s+", " ", prose_for_language)
    if re.search(r"[A-Za-z][A-Za-z0-9 ,.'’\-–—/:()]{160,}", prose_for_language):
        raise ValueError(f"translated README contains a long untranslated English passage: {path}")
    if "待翻译" in body or "TODO_TRANSLATE" in body:
        raise ValueError(f"translated README contains a placeholder: {path}")
    if body.count("```") % 2:
        raise ValueError(f"unbalanced fenced code block: {path}")
    source_bytes = int(entry.get("source_bytes", 0))
    translation_bytes = int(entry.get("translation_bytes", 0))
    if translation_bytes != len(body.encode("utf-8")):
        raise ValueError(f"translation byte count mismatch: {path}")
    if metadata["mode"] == "faithful-translation" and source_bytes and translation_bytes < source_bytes * 0.25:
        raise ValueError(f"translated README is too short for a faithful translation: {path}")

def featured_names(root: Path) -> set[str]:
    layout = WorkspaceLayout.discover(root)
    data_root = layout.data_root
    names: set[str] = set()
    structured_dates: set[str] = set()
    for path in sorted((data_root / "daily").glob("*.json")):
        edition = read_json(path)
        validate_daily_edition(edition)
        names.update(edition["displayed_projects"])
        structured_dates.add(path.stem)
    # Legacy adapter: historical repositories may only have Markdown daily files.
    for path in sorted((data_root / "daily").glob("*.md")):
        if path.stem in structured_dates:
            continue
        text = path.read_text(encoding="utf-8")
        names.update(re.findall(r"^### (.+?)\s*$", text, re.M))
    return names


def validate_translations(root: Path) -> dict[str, int]:
    project_root = root.resolve()
    root = WorkspaceLayout.discover(project_root).data_root
    catalog = read_json(root / "catalog.json")
    catalog_by_name = {entry["full_name"]: entry for entry in catalog.get("entries", [])}
    displayed_names = featured_names(project_root)
    if not displayed_names.issubset(catalog_by_name):
        raise ValueError("front-end featured projects are missing from catalog")
    manifest_path = root / "readmes" / "manifest.json"
    if not displayed_names and not manifest_path.exists():
        return {"projects": 0, "chinese_files": 0, "manifest_entries": 0, "missing": 0, "invalid": 0}
    if not manifest_path.is_file():
        raise ValueError("missing translation manifest: readmes/manifest.json")
    manifest = read_json(manifest_path)
    entries = manifest.get("entries", [])
    if manifest.get("schema_version") != 1 or manifest.get("entry_count") != len(entries):
        raise ValueError("translation manifest version or count mismatch")
    by_name = {entry.get("full_name"): entry for entry in entries}
    if set(by_name) != displayed_names:
        missing = sorted(displayed_names - set(by_name))
        extra = sorted(set(by_name) - displayed_names)
        raise ValueError(f"translation manifest/front-end mismatch missing={missing[:10]} extra={extra[:10]}")

    expected_paths: set[Path] = set()
    hashes: set[str] = set()
    for name in sorted(displayed_names, key=str.casefold):
        entry = by_name[name]
        expected = f"readmes/{name.replace('/', '__')}.zh-CN.md"
        if entry.get("translation") != expected:
            raise ValueError(f"translation path mismatch for {name}")
        path = root / expected
        if not path.is_file():
            raise ValueError(f"missing translation for {name}: {expected}")
        expected_paths.add(path.resolve())
        actual_hash = sha256(path)
        if actual_hash.lower() != str(entry.get("translation_sha256", "")).lower():
            raise ValueError(f"translation SHA-256 mismatch for {name}")
        validate_translation(path, entry)
        hashes.add(actual_hash)

    actual_paths = {path.resolve() for path in (root / "readmes").glob("*.zh-CN.md")}
    if actual_paths != expected_paths:
        raise ValueError("translated README files do not match catalog exactly")
    if len(hashes) != len(displayed_names):
        raise ValueError("duplicate translated README content detected")
    return {
        "projects": len(displayed_names),
        "chinese_files": len(actual_paths),
        "manifest_entries": len(entries),
        "missing": 0,
        "invalid": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate localized Chinese README artifacts")
    sub = parser.add_subparsers(dest="command", required=True)
    validate = sub.add_parser("validate")
    validate.add_argument("--root", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = validate_translations(args.root)
    except (KeyError, OSError, TypeError, ValueError) as exc:
        print(f"README VALIDATE FAIL {exc}")
        return 1
    print("README VALIDATE PASS " + " ".join(f"{key}={value}" for key, value in result.items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
