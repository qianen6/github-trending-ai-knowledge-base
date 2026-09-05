from __future__ import annotations
import hashlib
import json
from importlib.metadata import version
from pathlib import Path
from . import github_markdown
from .io_utils import atomic_json


class RenderCache:
    """Content-addressed rendered fragments; caller still validates each release."""

    def __init__(self, directory: Path, enabled: bool = True):
        self.directory = directory
        self.enabled = enabled
        self.hits = 0
        self.misses = 0
        self.renderer = hashlib.sha256(
            Path(github_markdown.__file__).read_bytes()
            + "|".join(
                version(p) for p in ("Markdown", "bleach", "beautifulsoup4")
            ).encode()
        ).hexdigest()

    def render(self, text: str) -> str:
        key = hashlib.sha256((self.renderer + "\n" + text).encode("utf-8")).hexdigest()
        path = self.directory / f"{key}.json"
        if self.enabled and path.is_file():
            try:
                cached = json.loads(path.read_text(encoding="utf-8"))
                output = cached["html"]
                if (
                    cached["sha256"]
                    == hashlib.sha256(output.encode("utf-8")).hexdigest()
                ):
                    self.hits += 1
                    return output
            except (OSError, ValueError, KeyError, TypeError):
                pass
        output = github_markdown.render_markdown(text)
        self.misses += 1
        if self.enabled:
            atomic_json(
                path,
                {
                    "html": output,
                    "sha256": hashlib.sha256(output.encode("utf-8")).hexdigest(),
                },
            )
        return output
