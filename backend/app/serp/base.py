"""The interface every SERP source implements.

Mirrors ``app/providers/base.py``: a source exposes ``name`` (recorded on every
stored observation, so a result can always be traced back to the instance that
produced it) and a single ``search(query)`` call returning a :class:`SerpPage`.

The one thing this interface insists on that the ``Provider`` one does not is
that **a page carries the evidence needed to trust it**. A metasearch instance
answers ``200 OK`` with an empty ``results`` list when every upstream engine
rate-limited or CAPTCHA'd it — that is not a rare edge, it is what a live
instance does on an ordinary day (measured: ``brave`` suspended, ``duckduckgo``
CAPTCHA, ``startpage`` suspended, all in one query). Reading that empty page as
"the brand ranks nowhere" would manufacture a zero out of a failed measurement,
and a fabricated zero is worse than no number at all in a product whose whole
wedge is showing its work. So a page also carries the engines that refused, and
:attr:`SerpPage.measurable` refuses to call an empty one evidence of absence.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


class SerpUnavailable(Exception):
    """The SERP source could not be reached, or answered unusably.

    Always caught by the pipeline. SERP visibility is an extra signal layered on
    a run that has already paid for discovery, KYC and the whole LLM panel, so a
    search instance being down, slow or misconfigured must degrade the run's
    SERP number to "not measured" — never fail the job (ADR-28).
    """


@dataclass(frozen=True)
class SerpResult:
    """One organic result at its merged rank across the instance's engines.

    ``rank`` is the position in the merged, score-ordered list the instance
    returns — not the per-engine ``positions`` array, which says where each
    upstream engine put the result and therefore cannot be compared across a
    metasearch page.
    """

    rank: int
    url: str
    title: str = ""
    content: str = ""
    engine: str = ""


@dataclass(frozen=True)
class SerpPage:
    """One query's results, plus what it would take to trust them."""

    query: str
    results: tuple[SerpResult, ...] = ()
    unresponsive_engines: tuple[str, ...] = ()
    # Autocomplete-style strings SearXNG may attach to the JSON payload. Used by
    # the keyword preview expander; empty when the instance/engines omit them.
    suggestions: tuple[str, ...] = ()
    # Instant-answer / PAA-like strings when the instance provides them.
    answers: tuple[str, ...] = ()

    @property
    def measurable(self) -> bool:
        """False when this page cannot support any claim about the brand.

        An empty page from a healthy instance is a real answer: nobody ranks for
        that query, and a miss is the honest reading. An empty page from an
        instance whose engines all refused to answer is not an answer at all,
        and scoring it as a miss invents a zero. Results present means the page
        is usable whatever else failed — a partial panel still ranked somebody.
        """
        return bool(self.results) or not self.unresponsive_engines


@runtime_checkable
class SerpSource(Protocol):
    name: str

    def search(self, query: str) -> SerpPage:
        ...
