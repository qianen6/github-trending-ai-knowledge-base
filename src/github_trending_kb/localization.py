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
from .io_utils import atomic_bytes, atomic_json

FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n", re.S)
REQUIRED_FRONTMATTER = {"full_name", "source_url", "source_sha256", "language", "mode"}


def markdown_structure(text: str) -> dict:
    from markdown_it import MarkdownIt

    normalized = text.replace("\r\n", "\n")
    lines = normalized.splitlines()
    blocks = []
    tokens = MarkdownIt().parse(normalized)
    for token in tokens:
        if token.type != "fence":
            continue
        end = lines[token.map[1] - 1] if token.map else ""
        if not re.fullmatch(
            r"[ \t>]*"
            + re.escape(token.markup[0])
            + "{"
            + str(len(token.markup))
            + r",}[ \t]*",
            end,
        ):
            raise ValueError("unbalanced fenced code block")
        blocks.append(token.info + "\n" + token.content)
    return {
        "blocks": blocks,
        "headings": [int(t.tag[1:]) for t in tokens if t.type == "heading_open"],
        "prose": " ".join(
            child.content
            for t in tokens
            for child in (t.children or [])
            if child.type == "text"
        ),
    }


def fenced_blocks(text: str) -> list[str]:
    return markdown_structure(text)["blocks"]


def heading_levels(text: str) -> list[int]:
    return markdown_structure(text)["headings"]


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
    text = re.sub(r"<!--[\s\S]*?-->", "", text)
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
    if entry.get("mode", metadata["mode"]) != metadata["mode"]:
        raise ValueError(f"localization mode mismatch: {path}")
    source_hash = metadata["source_sha256"].lower()
    if not re.fullmatch(r"[0-9a-f]{64}", source_hash):
        raise ValueError(f"invalid source SHA-256: {path}")
    source_path = path.parent / "sources" / f"{source_hash}.md"
    if not source_path.is_file():
        raise ValueError(f"missing source artifact: {source_path}")
    source_bytes_raw = source_path.read_bytes()
    if hashlib.sha256(source_bytes_raw).hexdigest() != source_hash:
        raise ValueError(f"source artifact SHA-256 mismatch: {path}")
    if int(entry.get("source_bytes", -1)) != len(source_bytes_raw):
        raise ValueError(f"source byte count mismatch: {path}")
    source = source_bytes_raw.decode("utf-8-sig").replace("\r\n", "\n")
    source_structure = markdown_structure(source)
    if metadata["mode"] == "source-copy":
        prose = source_structure["prose"]
        if chinese_prose_count(prose) < max(1, len(re.findall(r"[A-Za-z]{3,}", prose))):
            raise ValueError(
                f"source-copy requires Chinese-dominant original prose: {path}"
            )
        if body != source.strip():
            raise ValueError(f"source-copy differs from official source: {path}")
    else:
        translated_structure = markdown_structure(body)
        if translated_structure["blocks"] != source_structure["blocks"]:
            raise ValueError(
                f"translated README code blocks differ from source: {path}"
            )
        source_headings, translated_headings = (
            source_structure["headings"],
            translated_structure["headings"],
        )
        if (
            translated_headings != source_headings
            and translated_headings != [1] + source_headings
        ):
            raise ValueError(
                f"translated README heading structure differs from source: {path}"
            )
    has_markdown_title = bool(re.search(r"^# .+", body, re.M))
    # Chinese-dominant official READMEs must remain byte-for-byte source copies.
    # Some use a logo image or HTML block as the visual title, so requiring a
    # synthetic Markdown H1 would conflict with source-copy fidelity.
    if metadata["mode"] != "source-copy" and not has_markdown_title:
        raise ValueError(f"translated README needs title and sections: {path}")
    if chinese_prose_count(body) < (
        min(80, chinese_prose_count(source))
        if metadata["mode"] == "source-copy"
        else 80
    ):
        raise ValueError(f"translated README has insufficient Chinese prose: {path}")
    prose_for_language = re.sub(r"<!--[\s\S]*?-->", "", body)
    prose_for_language = re.sub(r"```[\s\S]*?```", "", prose_for_language)
    prose_for_language = "\n".join(
        line
        for line in prose_for_language.splitlines()
        if not line.lstrip().startswith(("|", ">"))
    )
    prose_for_language = re.sub(r"`[^`]+`", "", prose_for_language)
    prose_for_language = re.sub(r"data:[^\s)\"']+", "", prose_for_language)
    prose_for_language = re.sub(r"https?://\S+", "", prose_for_language)
    prose_for_language = re.sub(r"\s+", " ", prose_for_language)
    if re.search(r"[A-Za-z][A-Za-z0-9 ,.'’\-–—/:()]{160,}", prose_for_language):
        raise ValueError(
            f"translated README contains a long untranslated English passage: {path}"
        )
    if "待翻译" in body or "TODO_TRANSLATE" in body:
        raise ValueError(f"translated README contains a placeholder: {path}")
    if body.count("```") % 2:
        raise ValueError(f"unbalanced fenced code block: {path}")
    source_bytes = int(entry.get("source_bytes", 0))
    translation_bytes = int(entry.get("translation_bytes", 0))
    if translation_bytes != len(body.encode("utf-8")):
        raise ValueError(f"translation byte count mismatch: {path}")
    if (
        metadata["mode"] == "faithful-translation"
        and source_bytes
        and translation_bytes < source_bytes * 0.25
    ):
        raise ValueError(
            f"translated README is too short for a faithful translation: {path}"
        )


def featured_names(root: Path) -> set[str]:
    layout = WorkspaceLayout.discover(root)
    data_root = layout.data_root
    names: set[str] = set()
    for path in sorted((data_root / "daily").glob("*.json")):
        edition = read_json(path)
        validate_daily_edition(edition)
        names.update(edition["displayed_projects"])
    return names


def validate_translations(root: Path) -> dict[str, int]:
    project_root = root.resolve()
    root = WorkspaceLayout.discover(project_root).data_root
    catalog = read_json(root / "catalog.json")
    catalog_by_name = {
        entry["full_name"]: entry for entry in catalog.get("entries", [])
    }
    displayed_names = featured_names(project_root)
    if not displayed_names.issubset(catalog_by_name):
        raise ValueError("front-end featured projects are missing from catalog")
    manifest_path = root / "readmes" / "manifest.json"
    if not displayed_names and not manifest_path.exists():
        return {
            "projects": 0,
            "chinese_files": 0,
            "manifest_entries": 0,
            "missing": 0,
            "invalid": 0,
        }
    if not manifest_path.is_file():
        raise ValueError("missing translation manifest: readmes/manifest.json")
    manifest = read_json(manifest_path)
    entries = manifest.get("entries", [])
    if manifest.get("schema_version") != 1 or manifest.get("entry_count") != len(
        entries
    ):
        raise ValueError("translation manifest version or count mismatch")
    by_name = {entry.get("full_name"): entry for entry in entries}
    if len(by_name) != len(entries):
        raise ValueError("duplicate translation manifest full_name")
    if set(by_name) != displayed_names:
        missing = sorted(displayed_names - set(by_name))
        extra = sorted(set(by_name) - displayed_names)
        raise ValueError(
            f"translation manifest/front-end mismatch missing={missing[:10]} extra={extra[:10]}"
        )

    expected_paths: set[Path] = set()
    hashes: set[str] = set()
    for name in sorted(displayed_names, key=str.casefold):
        entry = by_name[name]
        expected_source = (
            f"readmes/sources/{str(entry.get('source_sha256', '')).lower()}.md"
        )
        if entry.get("source_artifact") != expected_source:
            raise ValueError(f"source artifact path mismatch for {name}")
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
        _, body = split_translation(path.read_text(encoding="utf-8-sig"))
        hashes.add(hashlib.sha256(body.encode("utf-8")).hexdigest())

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


def bind_sources(root: Path, source_dir: Path) -> dict[str, int]:
    """Bind immutable raw snapshots; never infer or generate translation prose."""
    layout = WorkspaceLayout.discover(root)
    folder = source_dir.resolve()
    if not folder.is_relative_to(layout.data_root.resolve()):
        raise ValueError("README sources must be below workspace")
    manifest = read_json(layout.readmes / "manifest.json")
    by_hash = {}
    for path in folder.rglob("*.md"):
        by_hash[sha256(path)] = path
    prepared = []
    for entry in manifest["entries"]:
        digest = entry["source_sha256"].lower()
        if digest not in by_hash:
            raise ValueError(f"matching raw README missing: {entry['full_name']}")
        raw = by_hash[digest].read_bytes()
        if len(raw) != entry["source_bytes"]:
            raise ValueError(f"raw README size mismatch: {entry['full_name']}")
        entry["source_artifact"] = f"readmes/sources/{digest}.md"
        prepared.append((layout.path(entry["source_artifact"]), raw))
    for path, raw in prepared:
        atomic_bytes(path, raw)
    atomic_json(layout.readmes / "manifest.json", manifest)
    return {"bound_sources": len(prepared)}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate localized Chinese README artifacts"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    validate = sub.add_parser("validate")
    validate.add_argument("--root", required=True, type=Path)
    bind = sub.add_parser("bind-sources")
    bind.add_argument("--root", required=True, type=Path)
    bind.add_argument("--source-dir", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = (
            bind_sources(args.root, args.source_dir)
            if args.command == "bind-sources"
            else validate_translations(args.root)
        )
    except (KeyError, OSError, TypeError, ValueError) as exc:
        print(f"README VALIDATE FAIL {exc}")
        return 1
    prefix = (
        "README SOURCES PASS "
        if args.command == "bind-sources"
        else "README VALIDATE PASS "
    )
    print(prefix + " ".join(f"{key}={value}" for key, value in result.items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
