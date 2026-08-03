"""Step 1 - discovery: fetch and extract the main text of a company website.

Fetches the homepage plus up to five same-domain HTML links (httpx, 15s timeout,
``YankiBot/0.1`` user agent; non-HTML, binary and oversized responses are
skipped), harvesting schema.org JSON-LD, page metadata (title, description,
keywords, Open Graph) and visible text from each. When a site renders almost no
server-side text (a Vite/React SPA), a fallback harvests same-origin JS bundles
and extracts human-readable string literals so single-page apps still yield real
content. The combined text is capped at ~20k characters; an unreachable or empty
site raises ``PipelineError``.

Four things this module does to keep that 20k budget honest
(docs/pipeline-quality-plan.md, workstream D):

* **Decode by the encoding the page declares.** httpx defaults to UTF-8 when the
  header carries no charset, which turns a windows-1254 Turkish page into
  mojibake that no later step can undo. A ``<meta charset>`` in the first bytes
  wins over that default; a header charset wins over both.
* **Sniff for binary.** Content-Type is trusted but missing headers fail open
  (matching ``net_guard``), so the first bytes are checked for the magic numbers
  of the formats sites actually link — a header-less PDF is skipped rather than
  parsed into mojibake.
* **Score links instead of matching them.** Content-ful paths (about, products,
  services, ... incl. Turkish equivalents, in the path *or* the anchor text) are
  crawled first; never-descriptive paths (login, cart, privacy, careers) are
  dropped outright; blog/news/search-type paths are demoted; deep paths are
  penalised; fragments are stripped so ``/about`` and ``/about#team`` are one
  page.
* **Read each block of copy once.** Sites repeat their header, footer and legal
  blurb on every page. Visible text is extracted as blocks and a block already
  seen earlier in the crawl is dropped, so the budget goes to the pages the
  first page did not already say.
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
from app.pipeline.textfold import fold

USER_AGENT = "YankiBot/0.1"
TIMEOUT_SECONDS = 15.0
MAX_LINKS = 5
MAX_CHARS = 20_000

# Per-page share of the budget for pages *after* the homepage, so one enormous
# product listing cannot starve the other four. The homepage is uncapped: on a
# single-page site it is the entire crawl.
MAX_PAGE_CHARS = 6_000

# The homepage is the one fetch whose failure ends the job, so a single reset
# connection or DNS blip gets one more chance. Same URL, no backoff beyond the
# client's own 15s timeout.
HOME_FETCH_ATTEMPTS = 2

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
MAX_PAGE_BYTES = 2_000_000

# Content types worth handing to an HTML parser. Anything else a link points at
# (PDF, image, zip) is skipped rather than turned into mojibake.
_HTML_CONTENT_TYPES = frozenset({"text/html", "application/xhtml+xml"})

# Magic numbers of the binary formats a website actually links. Checked because
# ``_is_html`` fails open on a *missing* Content-Type (a deliberate stance that
# matches net_guard), which used to let a header-less PDF through to the parser.
_BINARY_MAGIC = (
    b"%PDF",
    b"PK\x03\x04",  # zip, docx, xlsx, pptx
    b"\x89PNG",
    b"GIF8",
    b"\xff\xd8\xff",  # jpeg
    b"\x1f\x8b",  # gzip
    b"RIFF",  # webp / wav
    b"OggS",
    b"%!PS",  # postscript
    b"\x25\x50\x44",
)
_BINARY_SNIFF_BYTES = 512

# A page may declare its encoding only in the document. Read from the raw bytes,
# so this must be a bytes pattern.
_META_CHARSET_RE = re.compile(rb"""charset\s*=\s*["']?\s*([A-Za-z0-9_.:-]+)""")
_META_SNIFF_BYTES = 2_048
MIN_LITERAL_LEN = 20
# A genuine prose string literal is a sentence or two; anything longer is almost
# always a minified-code span that happens to fall between two backticks.
MAX_LITERAL_LEN = 600

# Path keywords that flag a content-ful page, English + Turkish (unaccented; see
# textfold.fold). Links matching these are crawled before generic first-seen.
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

# Paths that never describe what a company sells. Dropped outright rather than
# ranked last: there is no site on which /login is the sixth-best page.
_EXCLUDED_KEYWORDS = (
    "login",
    "signin",
    "sign-in",
    "signup",
    "register",
    "kayit",
    "account",
    "hesap",
    "cart",
    "sepet",
    "checkout",
    "basket",
    "privacy",
    "gizlilik",
    "kvkk",
    "terms",
    "cookie",
    "cerez",
    "policy",
    "career",
    "kariyer",
    "/jobs",
    "wp-admin",
    "wp-login",
)

# Paths that *may* carry company copy but usually carry a feed of unrelated
# posts. Demoted, never dropped — a small company's blog is sometimes the only
# place it explains itself.
_DEMOTED_KEYWORDS = (
    "blog",
    "news",
    "haber",
    "press",
    "basin",
    "event",
    "etkinlik",
    "faq",
    "sss",
    "search",
    "arama",
    "sitemap",
    "archive",
    "arsiv",
    "tag",
    "gallery",
    "galeri",
)

# Extensions whose bytes are not a web page. Cheaper (and quieter) to skip by
# path than to fetch and discover it from the Content-Type.
_EXCLUDED_EXTENSIONS = (
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".csv",
    ".zip", ".rar", ".7z", ".gz", ".tar", ".dmg", ".exe", ".apk",
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".ico", ".bmp",
    ".mp4", ".mp3", ".avi", ".mov", ".wav", ".webm",
    ".css", ".js", ".json", ".xml", ".rss", ".txt",
)

_PATH_KEYWORD_SCORE = 3
_ANCHOR_KEYWORD_SCORE = 2
_DEMOTION = 2

# "...", '...', or `...` literals (backticks are where Vite/React content lives).
_LITERAL_RE = re.compile(
    r'"([^"\\]*(?:\\.[^"\\]*)*)"'
    r"|'([^'\\]*(?:\\.[^'\\]*)*)'"
    r"|`([^`\\]*(?:\\.[^`\\]*)*)`",
    re.DOTALL,
)

_CODE_CHARS = set("{}();=<>$[]|&*+`\\/")

# Unambiguous JavaScript fragments. The character-ratio test below misses a
# minified span that happens to contain a lot of English — a framework's own
# error strings ("Did you accidentally import `RouterProvider` ...") are prose by
# every statistical measure, and they arrive welded to the code around them.
_CODE_TOKENS = (
    "=>",
    "){",
    "};",
    "==",
    "!=",
    "var ",
    "let ",
    "const ",
    "function(",
    "function (",
    "return ",
    "typeof ",
    "undefined",
    "null,",
    "props.",
    "this.",
)

# Diagnostics a framework runtime ships inside its bundle. They are prose by
# every statistical measure — full English sentences — so only their content
# gives them away. Deliberately phrases, not the bare word "react": a software
# agency's own copy may legitimately name the library.
_FRAMEWORK_PHRASES = (
    "react element",
    "react child",
    "react error",
    "react.children",
    "react-router",
    "did you accidentally",
    "expected to receive",
    "is not valid as a",
    "invalid hook call",
    "hydration",
    "webpack",
    "polyfill",
    "source map",
    "prop type",
    "is deprecated and will be removed",
)


def _visible_blocks(html: str) -> list[str]:
    """The page's visible text, one entry per text block.

    Blocks (rather than one flat string) are what makes cross-page boilerplate
    removable: a footer is the same block on every page, so keeping the first
    occurrence and dropping the rest loses no information and frees budget for
    copy the crawl has not seen yet.
    """
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "noscript"]):
        tag.decompose()
    blocks: list[str] = []
    for line in soup.get_text(separator="\n").splitlines():
        block = " ".join(line.split())
        if block:
            blocks.append(block)
    return blocks


def _clean_text(html: str) -> str:
    """The page's visible text as one string (blocks joined)."""
    return " ".join(_visible_blocks(html))


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


def _within_size(response: httpx.Response, limit: int) -> bool:
    """False when the response *declares* more bytes than we are willing to read."""
    length = response.headers.get("content-length")
    return not (length and length.isdigit() and int(length) > limit)


def _is_html(response: httpx.Response) -> bool:
    """True for HTML — and for a response that declares no type at all.

    ``_select_links`` happily picks a linked PDF or image, whose bytes would
    otherwise go through BeautifulSoup and ``_clean_text`` and whose mojibake
    would eat the MAX_CHARS budget that real page copy needed.

    Missing or empty Content-Type is treated as HTML on purpose. That is the
    codebase's existing fail-open stance — ``net_guard`` treats an unresolvable
    host as public so CI and offline dev keep working — and many respx fixtures
    set no header at all.
    """
    declared = response.headers.get("content-type", "")
    content_type = declared.split(";")[0].strip().casefold()
    return not content_type or content_type in _HTML_CONTENT_TYPES


def _looks_binary(raw: bytes) -> bool:
    """True when the first bytes are a known binary format (or contain a NUL).

    No ``text/html`` document begins with a NUL byte; a UTF-16-encoded page
    technically could, and is accepted collateral — it is vanishingly rare on
    the public web, and parsing a PDF as HTML is the failure we actually see.
    """
    head = raw[:_BINARY_SNIFF_BYTES]
    if not head:
        return False
    return head.startswith(_BINARY_MAGIC) or b"\x00" in head


def _decode(response: httpx.Response) -> str:
    """Decode a page with the encoding it declares, not with a guess.

    Precedence: the ``Content-Type`` charset (a server that states its encoding
    is authoritative), then a ``<meta charset>`` in the first bytes, then
    httpx's own default. Without the middle step a page served as bare
    ``text/html`` but authored in ISO-8859-9 / windows-1254 — still common on
    Turkish sites — arrives as mojibake that no later step can undo.
    """
    if "charset=" in response.headers.get("content-type", "").casefold():
        return response.text[:MAX_PAGE_BYTES]
    raw = response.content[:MAX_PAGE_BYTES]
    match = _META_CHARSET_RE.search(raw[:_META_SNIFF_BYTES])
    if match:
        try:
            return raw.decode(match.group(1).decode("ascii", "ignore"), errors="replace")
        except (LookupError, UnicodeDecodeError, ValueError):
            pass
    return response.text[:MAX_PAGE_BYTES]


def _fetch(client: httpx.Client, url: str, *, attempts: int = 1) -> str | None:
    """Fetch one page, or ``None`` for anything we should not parse.

    ``attempts`` > 1 retries only transport errors (never a 4xx/5xx, which is an
    answer rather than a failure to get one) and is used for the homepage, whose
    failure ends the whole job.
    """
    response: httpx.Response | None = None
    for attempt in range(max(1, attempts)):
        try:
            response = client.get(url)
            break
        except httpx.HTTPError:
            if attempt + 1 >= max(1, attempts):
                return None
    if response is None:
        return None
    if response.status_code != 200:
        return None
    if not _is_html(response):
        return None
    if not _within_size(response, MAX_PAGE_BYTES):
        return None
    if _looks_binary(response.content):
        return None
    return _decode(response)


def _fetch_script(client: httpx.Client, url: str) -> str | None:
    try:
        response = client.get(url)
    except httpx.HTTPError:
        return None
    if response.status_code != 200:
        return None
    if not _within_size(response, MAX_SCRIPT_BYTES):
        return None
    return response.text[:MAX_SCRIPT_BYTES]


def _link_score(link: str, anchor_text: str) -> int | None:
    """How worth crawling a link is; ``None`` to exclude it outright.

    Signals, in the order they are applied: a hard exclusion for non-document
    extensions and never-descriptive paths, a bonus per content keyword found in
    the path (and a smaller one for the anchor text, often the only signal on a
    site with opaque paths like ``/p/12``), a penalty for feed-ish paths, and a
    depth penalty so ``/products`` outranks ``/products/2019/archive/x``.
    """
    path = fold(urlparse(link).path)
    if path.endswith(_EXCLUDED_EXTENSIONS):
        return None
    if any(keyword in path for keyword in _EXCLUDED_KEYWORDS):
        return None

    text = fold(anchor_text)
    score = 0
    for keyword in _CONTENT_KEYWORDS:
        if keyword in path:
            score += _PATH_KEYWORD_SCORE
        elif keyword in text:
            score += _ANCHOR_KEYWORD_SCORE
    for keyword in _DEMOTED_KEYWORDS:
        if keyword in path:
            score -= _DEMOTION
    depth = len([segment for segment in path.split("/") if segment])
    return score - max(0, depth - 1)


def _normalized(link: str) -> str:
    """Comparison form of a URL: no fragment, no trailing slash."""
    return link.split("#")[0].rstrip("/")


def _select_links(base: str, home_html: str) -> list[str]:
    """Same-domain links, best-scoring first, then original order; capped.

    Fragments are stripped before de-duplication, so ``/about`` and
    ``/about#team`` are one page rather than two crawl slots.
    """
    soup = BeautifulSoup(home_html, "html.parser")
    base_key = _normalized(base)
    candidates: list[tuple[int, str]] = []
    seen: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        link = urljoin(base, anchor["href"]).split("#")[0]
        key = _normalized(link)
        if not link.startswith("http") or not _same_domain(base, link):
            continue
        if key == base_key or key in seen:
            continue
        score = _link_score(link, anchor.get_text(" ", strip=True))
        if score is None:
            continue
        seen.add(key)
        candidates.append((score, link))
    # Stable sort on the negated score keeps first-seen order within a tier, so
    # the crawl stays deterministic for a given page.
    ordered = [link for _, link in sorted(candidates, key=lambda item: -item[0])]
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
    if any(token in text for token in _CODE_TOKENS):
        return False
    folded = text.casefold()
    if any(phrase in folded for phrase in _FRAMEWORK_PHRASES):
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


def _fresh_text(blocks: list[str], seen: set[str], limit: int = 0) -> str:
    """Blocks not already seen earlier in the crawl, joined and optionally capped.

    ``seen`` is mutated: the first page to carry a block keeps it, every later
    page drops it. Comparison is folded + casefolded + whitespace-collapsed, so
    a footer that differs only in capitalization between two templates still
    collapses to one copy.
    """
    kept: list[str] = []
    length = 0
    for block in blocks:
        key = fold(block)
        if key in seen:
            continue
        seen.add(key)
        if limit:
            remaining = limit - length
            if remaining <= 0:
                break
            # Truncate rather than drop: a page whose whole body is one enormous
            # block (a product listing) should contribute its share, not zero.
            block = block[:remaining]
        kept.append(block)
        length += len(block) + 1
    return " ".join(kept)


def discover(url: str) -> str:
    headers = {"User-Agent": USER_AGENT}
    jsonld_parts: list[str] = []
    meta_parts: list[str] = []
    visible_parts: list[str] = []
    seen_blocks: set[str] = set()
    literal_text = ""
    with httpx.Client(
        timeout=TIMEOUT_SECONDS,
        headers=headers,
        follow_redirects=True,
        event_hooks={"request": [_guard_request]},
    ) as client:
        home_html = _fetch(client, url, attempts=HOME_FETCH_ATTEMPTS)
        if home_html is None:
            raise PipelineError("could not read the site")
        jsonld_parts.append(_jsonld_text(home_html))
        meta_parts.append(_meta_text(home_html))
        # The homepage is uncapped: on a single-page site it is the whole crawl.
        visible_parts.append(_fresh_text(_visible_blocks(home_html), seen_blocks))

        for link in _select_links(url, home_html):
            if sum(len(part) for part in visible_parts) >= MAX_CHARS:
                break
            page_html = _fetch(client, link)
            if page_html:
                jsonld_parts.append(_jsonld_text(page_html))
                meta_parts.append(_meta_text(page_html))
                visible_parts.append(
                    _fresh_text(_visible_blocks(page_html), seen_blocks, MAX_PAGE_CHARS)
                )

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
