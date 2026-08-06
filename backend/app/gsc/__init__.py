"""Google OAuth / Search Console seam (Phase 9 / M3).

Same shape as ``app/backlink`` and ``app/serp``: a Protocol, a deterministic
mock, a real adapter, and a registry that picks one from settings. Nothing here
touches the database or FastAPI — orchestration lives in
``app/services/search_console.py``.
"""
