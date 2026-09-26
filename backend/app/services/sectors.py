"""Stable spelling normalization for stored GEO sector labels."""

import unicodedata


def normalize_sector(value: str | None) -> str:
    """Normalize spelling only; never infer a question's topic or synonyms."""
    text = " ".join(unicodedata.normalize("NFKC", value or "").casefold().split())
    return "e-commerce" if text in {"e commerce", "ecommerce", "e-commerce"} else text
