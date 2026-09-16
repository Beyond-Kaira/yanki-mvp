"""Backward-compatible import path — prefer :mod:`app.keyword.serp_expand`."""

from __future__ import annotations

from app.keyword.serp_expand import SerpKeywordSource

SearxngKeywordSource = SerpKeywordSource

__all__ = ["SearxngKeywordSource", "SerpKeywordSource"]
