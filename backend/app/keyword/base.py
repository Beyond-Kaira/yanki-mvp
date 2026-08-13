"""The interface every keyword source implements.

Mirrors ``app/serp/base.py``: a source exposes ``name`` (so every idea can be
traced to the adapter that produced it) and ``expand(seed, …)`` returning a
:class:`KeywordExpandResult`.

This seam is the preview path described in ``docs/keyword-preview-oss.md``.
Live environments use SearXNG. Exact search volume and true KD are deliberately
absent here — later licensed adapters plug into the same protocol.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


class KeywordUnavailable(Exception):
    """The keyword source could not be reached, or answered unusably.

    Callers (future API routes) should surface this as a clear error — not
    invent rows. Unlike SERP visibility on an analysis run, keyword expand is
    the primary product of the request, so failure is visible rather than
    silently "not measured".
    """


@dataclass(frozen=True)
class KeywordIdea:
    """One candidate phrase derived from a seed.

    ``source`` records how it was found (``suggestion``, ``related``, ``paa``,
    ``variant``, ``mock``, …) so the UI can be honest about provenance.
    ``signals`` holds optional proxy scores later (demand/difficulty) without
    forcing every adapter to invent them up front.
    """

    phrase: str
    source: str
    signals: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class KeywordExpandResult:
    """Ideas for one seed + locale, plus enough context to debug the call."""

    seed: str
    locale: str
    ideas: tuple[KeywordIdea, ...] = ()
    provider: str = ""


@runtime_checkable
class KeywordSource(Protocol):
    name: str

    def expand(
        self,
        seed: str,
        *,
        locale: str = "en",
        max_ideas: int = 50,
        max_variants: int = 3,
        exclude_brands: Sequence[str] | None = None,
    ) -> KeywordExpandResult: ...
