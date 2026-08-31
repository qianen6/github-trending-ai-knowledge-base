#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import posixpath
import re
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlsplit


FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n", re.S)
REQUIRED_FRONTMATTER = {"full_name", "source_url", "source_sha256", "language", "mode"}
MARKDOWN_LINK_RE = re.compile(r"(!?)\[([^\]]*)\]\(([^)]+)\)")
NESTED_IMAGE_LINK_RE = re.compile(r"\[!\[([^\]]*)\]\(([^)]+)\)\]\(([^)]+)\)")
HTML_LINK_RE = re.compile(r"(?P<prefix>\b(?:href|src)=[\"'])(?P<target>[^\"']+)(?P<suffix>[\"'])", re.I)


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


def absolutize_markdown_links(body: str, full_name: str, branch: str, readme_path: str) -> str:
    base_dir = posixpath.dirname(readme_path)

    def absolute_target(target: str, image: bool) -> str:
        parts = urlsplit(target)
        if parts.scheme or target.startswith(("#", "//")):
            return target
        resolved = posixpath.normpath(posixpath.join(base_dir, parts.path))
        if resolved.startswith("../"):
            resolved = resolved.lstrip("./")
        if image:
            absolute = f"https://raw.githubusercontent.com/{full_name}/{quote(branch, safe='')}/{quote(resolved, safe='/')}"
        else:
            absolute = f"https://github.com/{full_name}/blob/{quote(branch, safe='')}/{quote(resolved, safe='/')}"
        if parts.query:
            absolute += f"?{parts.query}"
        if parts.fragment:
            absolute += f"#{parts.fragment}"
        return absolute

    def replace(match: re.Match[str]) -> str:
        marker, label, raw_target = match.groups()
        pieces = raw_target.strip().split(None, 1)
        target = pieces[0].strip("<>")
        title = f" {pieces[1]}" if len(pieces) > 1 else ""
        if urlsplit(target).scheme or target.startswith(("#", "//")):
            return match.group(0)
        absolute = absolute_target(target, marker == "!")
        return f"{marker}[{label}]({absolute}{title})"

    def replace_nested(match: re.Match[str]) -> str:
        alt, image_target, link_target = match.groups()
        return f"[![{alt}]({absolute_target(image_target, True)})]({absolute_target(link_target, False)})"

    normalized = NESTED_IMAGE_LINK_RE.sub(replace_nested, body)
    normalized = MARKDOWN_LINK_RE.sub(replace, normalized)

    def replace_html(match: re.Match[str]) -> str:
        prefix = match.group("prefix")
        target = match.group("target")
        image = prefix.lower().startswith("src=")
        return f"{prefix}{absolute_target(target, image)}{match.group('suffix')}"

    return HTML_LINK_RE.sub(replace_html, normalized)


def featured_names(root: Path) -> set[str]:
    names: set[str] = set()
    for path in sorted((root / "daily").glob("*.md")):
        text = path.read_text(encoding="utf-8")
        names.update(re.findall(r"^### (.+?)\s*$", text, re.M))
    return names


def validate_translations(root: Path) -> dict[str, int]:
    root = root.resolve()
    catalog = read_json(root / "catalog.json")
    catalog_by_name = {entry["full_name"]: entry for entry in catalog.get("entries", [])}
    displayed_names = featured_names(root)
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
