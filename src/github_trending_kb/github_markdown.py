from __future__ import annotations

import posixpath
import re
from urllib.parse import quote, urlsplit

import bleach
import markdown as markdown_lib
from bs4 import BeautifulSoup
from markdown.extensions.toc import slugify_unicode

MARKDOWN_LINK_RE = re.compile(r"(!?)\[([^\]]*)\]\(([^)]+)\)")
NESTED_IMAGE_LINK_RE = re.compile(r"\[!\[([^\]]*)\]\(([^)]+)\)\]\(([^)]+)\)")
HTML_LINK_RE = re.compile(r"(?P<prefix>\b(?:href|src)=[\"'])(?P<target>[^\"']+)(?P<suffix>[\"'])", re.I)
REFERENCE_DEF_RE = re.compile(
    r"^(?P<prefix>[ \t]{0,3}\[(?P<label>[^\]]+)\]:[ \t]*)(?P<target><[^>\n]+>|[^\s]+)(?P<suffix>[^\n]*)$",
    re.M,
)
IMAGE_REFERENCE_RE = re.compile(r"!\[(?P<alt>[^\]]*)\]\[(?P<label>[^\]]*)\]")

def absolutize_markdown_links(body: str, full_name: str, branch: str, readme_path: str) -> str:
    base_dir = posixpath.dirname(readme_path)
    image_reference_labels = {
        (match.group("label") or match.group("alt")).strip().casefold()
        for match in IMAGE_REFERENCE_RE.finditer(body)
    }

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

    def replace_reference(match: re.Match[str]) -> str:
        raw_target = match.group("target")
        target = raw_target.strip("<>")
        if urlsplit(target).scheme or target.startswith(("#", "//")):
            return match.group(0)
        image = match.group("label").strip().casefold() in image_reference_labels
        absolute = absolute_target(target, image)
        return f"{match.group('prefix')}{absolute}{match.group('suffix')}"

    normalized = REFERENCE_DEF_RE.sub(replace_reference, body)
    normalized = NESTED_IMAGE_LINK_RE.sub(replace_nested, normalized)
    normalized = MARKDOWN_LINK_RE.sub(replace, normalized)

    def replace_html(match: re.Match[str]) -> str:
        prefix = match.group("prefix")
        target = match.group("target")
        image = prefix.lower().startswith("src=")
        return f"{prefix}{absolute_target(target, image)}{match.group('suffix')}"

    return HTML_LINK_RE.sub(replace_html, normalized)

def _balance_alignment_divs(text: str) -> str:
    """Close common unbalanced README alignment divs before Markdown parsing."""
    output: list[str] = []
    open_alignment = 0
    for line in text.splitlines():
        if re.match(r"\s*<div\b[^>]*\balign\s*=", line, re.I):
            if open_alignment:
                output.extend("</div>" for _ in range(open_alignment))
                open_alignment = 0
            open_alignment += 1
        closing = len(re.findall(r"</div\s*>", line, re.I))
        open_alignment = max(0, open_alignment - closing)
        output.append(line)
    output.extend("</div>" for _ in range(open_alignment))
    return "\n".join(output)


def render_markdown(text: str) -> str:
    # Python-Markdown deliberately leaves Markdown inside raw HTML containers
    # untouched unless md_in_html is enabled per container. Official READMEs
    # commonly put tables, lists, badges, and fenced examples inside <details>
    # or alignment <div> blocks. Keep this normalization in one Module.
    text = _balance_alignment_divs(text)
    for container in ("details", "div"):
        text = re.sub(
            rf"<{container}(?![^>]*\bmarkdown\s*=)([^>]*)>",
            rf'<{container} markdown="1"\1>',
            text,
            flags=re.I,
        )
    rendered = markdown_lib.markdown(
        text,
        extensions=["extra", "sane_lists", "toc"],
        extension_configs={"toc": {"slugify": slugify_unicode, "permalink": False}},
        output_format="html5",
    )
    soup = BeautifulSoup(rendered, "html.parser")
    for unsafe in soup.find_all(["script", "style", "iframe", "object", "embed", "form"]):
        unsafe.decompose()
    cleaned = bleach.clean(
        str(soup),
        tags={
            "a", "blockquote", "br", "code", "del", "details", "div", "em", "h1", "h2", "h3", "h4", "h5", "h6",
            "hr", "img", "kbd", "li", "ol", "p", "picture", "pre", "source", "span", "strong", "sub", "summary",
            "sup", "table", "tbody", "td", "th", "thead", "tr", "ul", "video",
        },
        attributes={
            "*": ["id", "class", "align", "title"],
            "a": ["href", "target", "rel"],
            "img": ["src", "srcset", "alt", "width", "height", "loading"],
            "source": ["src", "srcset", "media", "type"],
            "video": ["src", "width", "height", "controls", "poster", "preload"],
            "details": ["open"],
            "td": ["width", "align", "colspan", "rowspan"],
            "th": ["width", "align", "colspan", "rowspan"],
            "table": ["align"],
        },
        protocols={"http", "https", "mailto"},
        strip=True,
    )
    soup = BeautifulSoup(cleaned, "html.parser")
    heading_by_text = {
        heading.get_text(" ", strip=True): heading.get("id")
        for heading in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"])
        if heading.get("id")
    }
    known_ids = {value for value in heading_by_text.values() if value}
    for link in soup.find_all("a", href=True):
        href = link["href"]
        if href.startswith("#") and href[1:] not in known_ids:
            matching = heading_by_text.get(link.get_text(" ", strip=True))
            if matching:
                link["href"] = f"#{matching}"
        elif href.startswith(("http://", "https://")):
            link["target"] = "_blank"
            link["rel"] = "noopener noreferrer"
    for image in soup.find_all("img"):
        image["loading"] = "lazy"
    for video in soup.find_all("video"):
        video["preload"] = "metadata"
    return str(soup)


def media_tags_in_markdown(text: str) -> set[str]:
    live = re.sub(r"```[\s\S]*?```|~~~[\s\S]*?~~~", "", text)
    live = re.sub(r"`[^`\n]*`", "", live)
    tags = {
        tag
        for tag in ("picture", "img", "video", "details", "table")
        if re.search(rf"<{tag}\b", live, re.I)
    }
    if re.search(r"!\[[^\]]*\]\([^)]+\)", live):
        tags.add("img")
    return tags
