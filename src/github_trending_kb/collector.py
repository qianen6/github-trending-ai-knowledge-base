from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Mapping, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup

from .domain import PERIOD_ORDER
from .io_utils import atomic_bytes, atomic_json, atomic_text
from .workspace import WorkspaceLayout


SCOPES = (
    "global",
    "python",
    "typescript",
    "javascript",
    "jupyter-notebook",
    "go",
    "rust",
)
PERIOD_QUERY = {"daily": "daily", "weekly": "weekly", "monthly": "monthly"}


@dataclass(frozen=True)
class TrendingPageSpec:
    scope: str
    period: str
    url: str

    @property
    def slug(self) -> str:
        return f"{self.scope}-{self.period}"


class FetchAdapter(Protocol):
    def fetch(self, url: str, headers: Mapping[str, str], timeout: float) -> bytes: ...


class UrllibFetchAdapter:
    def fetch(self, url: str, headers: Mapping[str, str], timeout: float) -> bytes:
        request = Request(url, headers=dict(headers))
        with urlopen(request, timeout=timeout) as response:
            return response.read()


class FixtureFetchAdapter:
    """Offline adapter used by replay tests and preserved capture fixtures."""

    def __init__(self, responses: Mapping[str, bytes | str]) -> None:
        self.responses = dict(responses)

    def fetch(self, url: str, headers: Mapping[str, str], timeout: float) -> bytes:
        if url not in self.responses:
            raise FileNotFoundError(f"fixture response missing: {url}")
        value = self.responses[url]
        return value.encode("utf-8") if isinstance(value, str) else value


def trending_page_matrix() -> list[TrendingPageSpec]:
    specs: list[TrendingPageSpec] = []
    for period in PERIOD_ORDER:
        for scope in SCOPES:
            language = "" if scope == "global" else f"/{scope}"
            specs.append(
                TrendingPageSpec(
                    scope=scope,
                    period=period,
                    url=f"https://github.com/trending{language}?since={PERIOD_QUERY[period]}&spoken_language_code=",
                )
            )
    return specs


def parse_number(text: str) -> int:
    match = re.search(r"(\d[\d,]*(?:\.\d+)?)\s*([kKmM])?\b", text)
    if not match:
        return 0
    value, suffix = match.groups()
    multiplier = {None: 1, "k": 1_000, "K": 1_000, "m": 1_000_000, "M": 1_000_000}[suffix]
    return int(float(value.replace(",", "")) * multiplier)


def parse_trending_html(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    entries: list[dict] = []
    for rank, article in enumerate(soup.select("article.Box-row"), start=1):
        repo_link = article.select_one("h2 a[href]")
        if repo_link is None:
            continue
        full_name = repo_link.get("href", "").strip("/")
        if full_name.count("/") != 1:
            continue
        description = article.select_one("p.col-9") or article.select_one("p")
        language = article.select_one('[itemprop="programmingLanguage"]')
        star_link = article.select_one(f'a[href="/{full_name}/stargazers"]')
        fork_link = article.select_one(f'a[href="/{full_name}/forks"]')
        period_node = article.select_one("span.float-sm-right")
        built_by = [
            image.get("alt", "").lstrip("@")
            for image in article.select('span.d-inline-block img[alt]')
            if image.get("alt")
        ]
        period_text = period_node.get_text(" ", strip=True) if period_node else ""
        entries.append(
            {
                "rank": rank,
                "full_name": full_name,
                "url": f"https://github.com/{full_name}",
                "description": description.get_text(" ", strip=True) if description else "",
                "primary_language": language.get_text(" ", strip=True) if language else None,
                "total_stars": parse_number(star_link.get_text(" ", strip=True)) if star_link else 0,
                "total_forks": parse_number(fork_link.get_text(" ", strip=True)) if fork_link else 0,
                "period_stars": parse_number(period_text) if period_text else None,
                "built_by": built_by,
            }
        )
    return entries


class TrendingCollector:
    def __init__(
        self,
        root: Path,
        adapter: FetchAdapter | None = None,
        *,
        retries: int = 3,
        timeout: float = 30.0,
        retry_delay: float = 1.0,
    ) -> None:
        self.layout = WorkspaceLayout.discover(root)
        self.adapter = adapter or UrllibFetchAdapter()
        self.retries = retries
        self.timeout = timeout
        self.retry_delay = retry_delay
        token = os.environ.get("GITHUB_TOKEN")
        self.headers = {
            "User-Agent": "github-trending-ai-knowledge-base/5",
            "Accept": "text/html,application/vnd.github+json",
        }
        if token:
            self.headers["Authorization"] = f"Bearer {token}"

    def _fetch(self, url: str) -> bytes:
        last: Exception | None = None
        for attempt in range(1, self.retries + 1):
            try:
                return self.adapter.fetch(url, self.headers, self.timeout)
            except (HTTPError, URLError, OSError) as exc:
                last = exc
                if attempt < self.retries:
                    time.sleep(self.retry_delay * attempt)
        assert last is not None
        raise last

    def collect_page(self, spec: TrendingPageSpec, capture_date: date, refresh: bool) -> dict:
        html_path = self.layout.path(
            Path("trending/html") / capture_date.isoformat() / f"{spec.slug}.html"
        )
        captured_at = datetime.now(timezone.utc).isoformat()
        try:
            body = html_path.read_bytes() if html_path.is_file() and not refresh else self._fetch(spec.url)
            if refresh or not html_path.is_file():
                html_path.parent.mkdir(parents=True, exist_ok=True)
                atomic_bytes(html_path, body)
            raw = html_path.read_bytes()
            entries = parse_trending_html(raw.decode("utf-8", errors="replace"))
            return {
                "scope": spec.scope,
                "period": spec.period,
                "spoken_language": "any",
                "source_url": spec.url,
                "captured_at": captured_at,
                "raw_sha256": hashlib.sha256(raw).hexdigest(),
                "status": "success",
                "entries": entries,
            }
        except Exception as exc:
            error = {
                "scope": spec.scope,
                "period": spec.period,
                "spoken_language": "any",
                "source_url": spec.url,
                "captured_at": captured_at,
                "raw_sha256": hashlib.sha256(str(exc).encode()).hexdigest(),
                "status": "failed",
                "entries": [],
                "_collection_error": f"{type(exc).__name__}: {exc}",
            }
            return error

    def collect_pages(
        self, capture_date: date, *, refresh: bool = False, max_workers: int = 7
    ) -> list[dict]:
        specs = trending_page_matrix()
        pages: dict[str, dict] = {}
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {
                pool.submit(self.collect_page, spec, capture_date, refresh): spec
                for spec in specs
            }
            for future in as_completed(futures):
                spec = futures[future]
                pages[spec.slug] = future.result()
        return [pages[spec.slug] for spec in specs]

    def collect_evidence(self, full_name: str, capture_date: date, refresh: bool = False) -> dict:
        slug = full_name.replace("/", "__")
        base = self.layout.path(Path("trending/evidence") / capture_date.isoformat() / slug)
        manifest_path = base / "manifest.json"
        if manifest_path.is_file() and not refresh:
            cached = json.loads(manifest_path.read_text(encoding="utf-8"))
            if all(record.get("status") == "success" for record in cached.get("records", [])):
                return cached
        if not refresh:
            prior = sorted(
                path
                for path in self.layout.path("trending/evidence").glob(
                    f"*/{slug}/manifest.json"
                )
                if path.parent.parent.name < capture_date.isoformat()
            )
            if prior:
                cached = json.loads(prior[-1].read_text(encoding="utf-8"))
                if all(record.get("status") == "success" for record in cached.get("records", [])):
                    return {
                        **cached,
                        "reused": True,
                        "reused_from": prior[-1].relative_to(self.layout.data_root).as_posix(),
                    }
        endpoints = {
            "repository": f"https://api.github.com/repos/{full_name}",
            "readme": f"https://api.github.com/repos/{full_name}/readme",
            "license": f"https://api.github.com/repos/{full_name}/license",
            "root_contents": f"https://api.github.com/repos/{full_name}/contents",
        }
        records = []
        base.mkdir(parents=True, exist_ok=True)
        for label, url in endpoints.items():
            try:
                body = self._fetch(url)
                path = base / f"{label}.json"
                atomic_text(path, body.decode("utf-8", errors="replace"))
                records.append(
                    {"kind": label, "url": url, "status": "success", "sha256": hashlib.sha256(body).hexdigest(), "path": path.relative_to(self.layout.data_root).as_posix()}
                )
            except Exception as exc:
                records.append({"kind": label, "url": url, "status": "failed", "error": f"{type(exc).__name__}: {exc}"})
        manifest = {
            "schema_version": 1,
            "full_name": full_name,
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "records": records,
        }
        atomic_json(manifest_path, manifest)
        return manifest

    def collect(
        self,
        capture_date: date,
        *,
        refresh: bool = False,
        evidence: bool = False,
        max_workers: int = 7,
    ) -> dict:
        collected_pages = self.collect_pages(capture_date, refresh=refresh, max_workers=max_workers)
        failures = [
            {
                "scope": page["scope"],
                "period": page["period"],
                "error": page["_collection_error"],
            }
            for page in collected_pages
            if "_collection_error" in page
        ]
        pages = [
            {key: value for key, value in page.items() if key != "_collection_error"}
            for page in collected_pages
        ]
        names = sorted(
            {entry["full_name"] for page in pages for entry in page["entries"]},
            key=str.casefold,
        )
        evidence_index: list[dict] = []
        if evidence:
            with ThreadPoolExecutor(max_workers=max_workers) as pool:
                futures = {
                    pool.submit(self.collect_evidence, name, capture_date, refresh): name
                    for name in names
                }
                for future in as_completed(futures):
                    evidence_index.append(future.result())
            evidence_index.sort(key=lambda item: item["full_name"].casefold())
        result = {
            "schema_version": 1,
            "capture_date": capture_date.isoformat(),
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "page_count": len(pages),
            "successful_pages": sum(page["status"] == "success" for page in pages),
            "candidate_count": len(names),
            "pages": pages,
            "repository_names": names,
            "evidence": evidence_index,
            "evidence_failures": sum(
                record.get("status") == "failed"
                for item in evidence_index
                for record in item.get("records", [])
            ),
            "failures": failures,
        }
        output = self.layout.path(
            Path("proof") / f"run-{capture_date.isoformat()}" / "collection.json"
        )
        atomic_json(output, result)
        return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect the fixed GitHub Trending matrix")
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--date", type=date.fromisoformat, default=date.today())
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--evidence", action="store_true")
    parser.add_argument("--workers", type=int, default=7)
    args = parser.parse_args()
    result = TrendingCollector(args.root).collect(
        args.date,
        refresh=args.refresh,
        evidence=args.evidence,
        max_workers=max(1, args.workers),
    )
    complete = (
        result["successful_pages"] == result["page_count"]
        and result["evidence_failures"] == 0
    )
    print(
        f"COLLECT {'PASS' if complete else 'PARTIAL'} "
        f"pages={result['page_count']} success={result['successful_pages']} "
        f"candidates={result['candidate_count']} evidence={len(result['evidence'])} "
        f"evidence_failures={result['evidence_failures']}"
    )
    return 0 if complete else 2
