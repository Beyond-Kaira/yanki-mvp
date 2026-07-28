"""Step 1 - discovery: fetch and extract the main text of a company website.

Fetches the homepage plus up to five same-domain links (httpx, 15s timeout,
``YankiBot/0.1`` user agent), harvesting schema.org JSON-LD, page metadata
(title, description, keywords, Open Graph) and visible text from each.
Content-ful links (about, products, services, ... incl. Turkish equivalents) are
preferred over first-seen order. When a site renders almost no server-side text
(a Vite/React SPA), a fallback harvests same-origin JS bundles and extracts
human-readable string literals so single-page apps still yield real content. The
combined text is capped at ~20k characters; an unreachable or empty site raises
``PipelineError``.
"""

from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup, Tag

from app.net_guard import is_public_host
from app.pipeline.errors import PipelineError

USER_AGENT = "YankiBot/0.1"
TIMEOUT_SECONDS = 15.0
MAX_LINKS = 5
MAX_CHARS = 20_000

# JSON-LD is dense and high-signal, but it must never crowd out the page copy:
# it is placed first in the combined text, so it gets a hard budget of its own.
MAX_JSONLD_CHARS = 4_000
MAX_JSONLD_DEPTH = 6

# schema.org keys worth harvesting — the ones that map onto the KYC model
# (company, aliases, description, products, locations). Everything else in a
# block is markup plumbing (@context, breadcrumbs, ratings) that only costs
# budget. ``sameAs`` is read as text only; discovery never follows those URLs.
_JSONLD_KEYS = frozenset(
    {
        "name",
        "legalName",
        "alternateName",
        "description",
        "slogan",
        "brand",
        "sameAs",
        "addressLocality",
        "addressCountry",
    }
)

# SPA fallback: when the visible text of the crawl is thinner than this, the site
# is almost certainly client-rendered, so we mine its JS bundles for content.
SPA_TEXT_THRESHOLD = 800
MAX_SCRIPTS = 3
MAX_SCRIPT_BYTES = 2_000_000
MIN_LITERAL_LEN = 20
# A genuine prose string literal is a sentence or two; anything longer is almost
# always a minified-code span that happens to fall between two backticks.
MAX_LITERAL_LEN = 600

# Path keywords that flag a content-ful page, English + Turkish (unaccented; see
# _fold). Links whose path matches these are crawled before generic first-seen.
_CONTENT_KEYWORDS = (
    "about",
    "company",
    "product",
    "service",
    "solution",
    "team",
    "technology",
    "hakkinda",
    "hakkimizda",
    "kurumsal",
    "urun",
    "urunler",
    "hizmet",
    "hizmetler",
    "cozum",
    "cozumler",
    "teknoloji",
)

# Fold Turkish diacritics to ASCII so "ürünler"/"çözüm" match the keyword list.
_TR_FOLD = str.maketrans(
    {
        "ç": "c",
        "ğ": "g",
        "ı": "i",
        "ö": "o",
        "ş": "s",
        "ü": "u",
        "â": "a",
        "î": "i",
        "û": "u",
    }
)

# "...", '...', or `...` literals (backticks are where Vite/React content lives).
_LITERAL_RE = re.compile(
    r'"([^"\\]*(?:\\.[^"\\]*)*)"'
    r"|'([^'\\]*(?:\\.[^'\\]*)*)'"
    r"|`([^`\\]*(?:\\.[^`\\]*)*)`",
    re.DOTALL,
)

_CODE_CHARS = set("{}();=<>$[]|&*+`\\/")


def _fold(text: str) -> str:
    return text.casefold().translate(_TR_FOLD)


def _clean_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "noscript"]):
        tag.decompose()
    return " ".join(soup.get_text(separator=" ", strip=True).split())


def _jsonld_strings(value: Any) -> list[str]:
    """The string leaves of a JSON-LD value.

    Handles the three shapes schema.org uses interchangeably for one field:
    ``"x"``, ``["x", "y"]`` and ``{"@type": "Brand", "name": "x"}``.
    """
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str)]
    if isinstance(value, dict):
        name = value.get("name")
        return [name] if isinstance(name, str) else []
    return []


def _collect_jsonld(node: Any, out: list[str], depth: int = 0) -> None:
    """Depth-bounded walk collecting the KYC-shaped values of a parsed block.

    Recursing into every container value handles ``@graph``, top-level arrays
    and nested ``Organization``/``Product`` nodes without special-casing them.
    """
    if depth > MAX_JSONLD_DEPTH:
        return
    if isinstance(node, list):
        for item in node:
            _collect_jsonld(item, out, depth + 1)
        return
    if not isinstance(node, dict):
        return
    for key, value in node.items():
        if key in _JSONLD_KEYS:
            for text in _jsonld_strings(value):
                cleaned = " ".join(text.split())
                if cleaned:
                    out.append(cleaned)
        if isinstance(value, dict | list):
            _collect_jsonld(value, out, depth + 1)


def _jsonld_text(html: str) -> str:
    """Flatten ``application/ld+json`` blocks into a bounded text segment.

    ``_clean_text`` decomposes every ``<script>``, which throws away the
    schema.org markup SEO tooling puts on most commercial sites — usually the
    cleanest statement of who the company is that a page carries. This is a
    second, *fetch-free* read of the same bytes; each block is parsed in its own
    ``try`` so one malformed block does not cost us the others.
    """
    soup = BeautifulSoup(html, "html.parser")
    values: list[str] = []
    for tag in soup.find_all("script", type="application/ld+json"):
        raw = tag.string or tag.get_text()
        if not raw or not raw.strip():
            continue
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            continue
        _collect_jsonld(data, values)
    return " ".join(dict.fromkeys(values))[:MAX_JSONLD_CHARS]


def _meta_text(html: str) -> str:
    """Harvest title + description/keywords + Open Graph tags (cheap signal)."""
    soup = BeautifulSoup(html, "html.parser")
    bits: list[str] = []
    if soup.title and soup.title.string:
        bits.append(soup.title.string.strip())

    def _meta(**attrs: str) -> None:
        tag = soup.find("meta", attrs=attrs)
        if isinstance(tag, Tag):
            content = tag.get("content")
            if isinstance(content, str) and content.strip():
                bits.append(content.strip())

    _meta(**{"name": "description"})
    _meta(**{"name": "keywords"})
    for prop in ("og:title", "og:description", "og:site_name"):
        _meta(**{"property": prop})
        _meta(**{"name": prop})
    return " ".join(dict.fromkeys(b for b in bits if b))


def _guard_request(request: httpx.Request) -> None:
    """Block SSRF: refuse to fetch a host that resolves to a non-public address.

    Registered as an httpx ``request`` event hook so it also fires on every
    redirect hop and on every bundle fetch — a public URL cannot 302 the worker
    into internal space, and a mined ``<script src>`` cannot either.
    """
    if not is_public_host(request.url.host):
        raise PipelineError("could not read the site")


def _same_domain(base: str, link: str) -> bool:
    return urlparse(base).netloc == urlparse(link).netloc


def _fetch(client: httpx.Client, url: str) -> str | None:
    try:
        response = client.get(url)
    except httpx.HTTPError:
        return None
    if response.status_code != 200:
        return None
    return response.text


def _fetch_script(client: httpx.Client, url: str) -> str | None:
    try:
        response = client.get(url)
    except httpx.HTTPError:
        return None
    if response.status_code != 200:
        return None
    length = response.headers.get("content-length")
    if length and length.isdigit() and int(length) > MAX_SCRIPT_BYTES:
        return None
    return response.text[:MAX_SCRIPT_BYTES]


def _is_content_link(link: str) -> bool:
    folded = _fold(urlparse(link).path)
    return any(keyword in folded for keyword in _CONTENT_KEYWORDS)


def _select_links(base: str, home_html: str) -> list[str]:
    """Same-domain links, content-ful paths first, then original order; capped."""
    soup = BeautifulSoup(home_html, "html.parser")
    all_links: list[str] = []
    for anchor in soup.find_all("a", href=True):
        link = urljoin(base, anchor["href"])
        if (
            link.startswith("http")
            and _same_domain(base, link)
            and link != base
            and link not in all_links
        ):
            all_links.append(link)
    preferred = [link for link in all_links if _is_content_link(link)]
    ordered = preferred + [link for link in all_links if link not in preferred]
    return ordered[:MAX_LINKS]


def _script_urls(base: str, home_html: str) -> list[str]:
    """Same-origin bundle URLs: <script src> and <link rel=modulepreload href>."""
    soup = BeautifulSoup(home_html, "html.parser")
    candidates: list[str] = []
    for tag in soup.find_all("script", src=True):
        candidates.append(urljoin(base, tag["src"]))
    for tag in soup.find_all("link", href=True):
        rel = tag.get("rel") or []
        rels = rel if isinstance(rel, list) else [rel]
        if any(str(value).lower() == "modulepreload" for value in rels):
            candidates.append(urljoin(base, tag["href"]))
    urls: list[str] = []
    for url in candidates:
        if url.startswith("http") and _same_domain(base, url) and url not in urls:
            urls.append(url)
    return urls[:MAX_SCRIPTS]


def _looks_like_prose(text: str) -> bool:
    """True for human-readable content; False for URLs, paths, and minified code."""
    if not MIN_LITERAL_LEN <= len(text) <= MAX_LITERAL_LEN:
        return False
    if text[0] in "/.#":
        return False
    if "://" in text:
        return False
    if text.casefold().startswith("data:"):
        return False
    if sum(char in _CODE_CHARS for char in text) / len(text) > 0.30:
        return False
    prose = sum(char.isalpha() or char.isspace() for char in text)
    if prose / len(text) < 0.55:
        return False
    return len(text.split()) >= 3


def _unescape(text: str) -> str:
    text = (
        text.replace("\\n", " ")
        .replace("\\r", " ")
        .replace("\\t", " ")
        .replace('\\"', '"')
        .replace("\\'", "'")
        .replace("\\`", "`")
        .replace("\\\\", "\\")
    )
    return " ".join(text.split())


def _prioritise(literals: list[str]) -> list[str]:
    """Localized (non-ASCII) site content first, then the rest, order preserved.

    A production JS bundle inlines the framework runtime (always ASCII English —
    React/router error strings) alongside the site's own copy. On a Turkish site
    the real content carries Turkish letters, so surfacing non-ASCII literals
    first keeps genuine content ahead of framework noise when the combined text
    is truncated to ``MAX_CHARS``.
    """
    localized = [text for text in literals if any(ord(ch) > 127 for ch in text)]
    localized_set = set(localized)
    ascii_only = [text for text in literals if text not in localized_set]
    return localized + ascii_only


def _extract_literals(js: str) -> list[str]:
    literals: list[str] = []
    seen: set[str] = set()
    for match in _LITERAL_RE.finditer(js):
        raw = match.group(1) or match.group(2) or match.group(3) or ""
        text = _unescape(raw)
        if _looks_like_prose(text) and text not in seen:
            seen.add(text)
            literals.append(text)
    return literals


def discover(url: str) -> str:
    headers = {"User-Agent": USER_AGENT}
    jsonld_parts: list[str] = []
    meta_parts: list[str] = []
    visible_parts: list[str] = []
    literal_text = ""
    with httpx.Client(
        timeout=TIMEOUT_SECONDS,
        headers=headers,
        follow_redirects=True,
        event_hooks={"request": [_guard_request]},
    ) as client:
        home_html = _fetch(client, url)
        if home_html is None:
            raise PipelineError("could not read the site")
        jsonld_parts.append(_jsonld_text(home_html))
        meta_parts.append(_meta_text(home_html))
        visible_parts.append(_clean_text(home_html))

        for link in _select_links(url, home_html):
            if sum(len(part) for part in visible_parts) >= MAX_CHARS:
                break
            page_html = _fetch(client, link)
            if page_html:
                jsonld_parts.append(_jsonld_text(page_html))
                meta_parts.append(_meta_text(page_html))
                visible_parts.append(_clean_text(page_html))

        visible_text = " ".join(part for part in visible_parts if part).strip()

        # SPA fallback: almost no server-rendered text -> mine the JS bundles.
        if len(visible_text) < SPA_TEXT_THRESHOLD:
            literals: list[str] = []
            for script_url in _script_urls(url, home_html):
                js = _fetch_script(client, script_url)
                if js:
                    literals.extend(_extract_literals(js))
            literal_text = " ".join(_prioritise(list(dict.fromkeys(literals))))

    # Sites repeat the same Organization block on every page, so dedupe before
    # spending the budget. JSON-LD leads: it is the densest, most factual part
    # of the crawl, and leading means it survives the MAX_CHARS cut.
    jsonld_text = " ".join(dict.fromkeys(part for part in jsonld_parts if part))
    combined = " ".join(
        part
        for part in [
            jsonld_text[:MAX_JSONLD_CHARS],
            *meta_parts,
            " ".join(visible_parts).strip(),
            literal_text,
        ]
        if part.strip()
    ).strip()
    if not combined:
        raise PipelineError("could not read the site")
    return combined[:MAX_CHARS]
