"""Conservative URL identity and search-evidence validation; no network requests."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import unquote_plus, urlsplit, urlunsplit

TRACKING_KEYS = {"gclid", "fbclid", "msclkid", "dclid"}


def canonical_url(raw: Any) -> str | None:
    if not isinstance(raw, str) or not raw or any(ord(c) < 33 for c in raw):
        return None
    try:
        parsed = urlsplit(raw)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return None
        if parsed.username is not None or parsed.password is not None or "\\" in raw:
            return None
        host = parsed.hostname.encode("idna").decode("ascii").lower()
        if ":" in host:
            host = f"[{host}]"
        port = parsed.port
        if port and (parsed.scheme, port) not in {("http", 80), ("https", 443)}:
            host += f":{port}"
        # Preserve meaningful query order, duplicate keys and escaping exactly.
        query = "&".join(
            part
            for part in parsed.query.split("&")
            if part
            and not (key := unquote_plus(part.split("=", 1)[0]).lower()).startswith("utm_")
            and key not in TRACKING_KEYS
        )
        return urlunsplit((parsed.scheme, host, parsed.path or "/", query, ""))
    except (ValueError, UnicodeError):
        return None


def result_rank(value: Any) -> int | None:
    # No bool, float truncation, or guessed positional fallback.
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        return None
    text = str(value)
    return int(text) if re.fullmatch(r"[1-9][0-9]{0,5}", text) else None


def result_lookup(results: Any) -> dict[int, dict[str, Any]]:
    if isinstance(results, dict):
        results = results.get("results")
    lookup: dict[int, dict[str, Any]] = {}
    ambiguous: set[int] = set()
    for source in results if isinstance(results, list) else []:
        if not isinstance(source, dict):
            continue
        rank = result_rank(source.get("rank"))
        if rank is None:
            continue
        if rank in lookup:
            ambiguous.add(rank)
        lookup[rank] = source
    return {rank: source for rank, source in lookup.items() if rank not in ambiguous}


def inline_ranks(answer: str) -> set[int]:
    """Accept the requested [1] format and grouped references such as [1, 2]."""
    ranks: set[int] = set()
    for group in re.findall(r"\[(\d+(?:\s*,\s*\d+)*)\]", answer):
        for value in group.split(","):
            if (rank := result_rank(value.strip())) is not None:
                ranks.add(rank)
    return ranks


def domain_matches(host: str, domains: set[str]) -> bool:
    return any(host == domain or host.endswith("." + domain) for domain in domains)
