"""Binary footprint detection: does the company appear in a raw answer?

Pure, deterministic, case-insensitive matching over the company name and its
aliases (which include the registrable domain name) — no LLM. Terms are matched
on word boundaries (``\\b``), not raw substrings, so a short term like ``GE`` or
``Co`` never counts as a hit inside an unrelated word (``general``, ``compare``).
On a hit it returns a short snippet of context around the first match.

Two tolerances sit on top of that, because a brand is written more than one way
and a missed match is a silently-too-low GEO score:

* **Diacritics are folded on both sides** (``textfold``), so ``TÜRK`` matches the
  alias ``Turk`` and ``İşbank`` matches ``Isbank``. Case alone already worked —
  ``re.IGNORECASE`` on ``str`` patterns is Unicode-aware — but folding was not
  happening at all.
* **Hyphen and space are interchangeable**, so ``Coca-Cola`` matches
  ``Coca Cola`` (and Hewlett-Packard, T-Mobile, ...).

Deliberately *not* tolerated: suffixation (``Yankinin`` for ``Yanki``). That is
agglutinative-suffix handling, which is deferred roadmap scope (§2c) awaiting an
operator decision — see docs/discovery-kyc-improvements.md step 2b.

The ``_MIN_TERM_LEN`` floor and the word-boundary anchor are what keep these
tolerances from manufacturing false positives on very short brands.
"""

from __future__ import annotations

import re

from app.pipeline.textfold import fold_ascii

_SNIPPET_RADIUS = 60
_MIN_TERM_LEN = 2

# Runs of hyphen/whitespace, which a brand may be written with or without.
_SEPARATORS = re.compile(r"[-\s]+")


def _terms(kyc) -> list[str]:
    """Distinct, non-trivial search terms drawn from the KYC profile."""
    seen: list[str] = []
    lowered: set[str] = set()
    for value in [kyc.company, *kyc.aliases]:
        term = (value or "").strip()
        if len(term) >= _MIN_TERM_LEN and term.lower() not in lowered:
            seen.append(term)
            lowered.add(term.lower())
    return seen


def _pattern(term: str) -> re.Pattern[str] | None:
    """Word-boundary pattern for one term, separator-tolerant; ``None`` if empty.

    The term is folded with the same map applied to the answer text, and its
    internal hyphens/spaces become ``[-\\s]+`` so either spelling hits.
    """
    parts = [re.escape(part) for part in _SEPARATORS.split(fold_ascii(term)) if part]
    if not parts:
        return None
    return re.compile(r"\b" + r"[-\s]+".join(parts) + r"\b", re.IGNORECASE)


def detect(raw_text: str, kyc) -> tuple[bool, str | None]:
    """Return ``(True, snippet)`` if the company appears, else ``(False, None)``."""
    if not raw_text:
        return False, None

    # Fold the answer with the same length-preserving map used on the terms, so
    # a match index still points at the right character of the original — the
    # snippet is sliced from ``raw_text`` and must keep its real spelling.
    folded_text = fold_ascii(raw_text)

    best_index: int | None = None
    best_len = 0
    for term in _terms(kyc):
        pattern = _pattern(term)
        if pattern is None:
            continue
        match = pattern.search(folded_text)
        if match and (best_index is None or match.start() < best_index):
            best_index = match.start()
            best_len = match.end() - match.start()

    if best_index is None:
        return False, None

    start = max(0, best_index - _SNIPPET_RADIUS)
    end = min(len(raw_text), best_index + best_len + _SNIPPET_RADIUS)
    return True, raw_text[start:end]
