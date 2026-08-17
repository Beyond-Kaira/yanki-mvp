"""Locale → Google Ads language / geo constants (first slice)."""

from __future__ import annotations

# languageConstants / geoTargetConstants resource names used by Keyword Planning.
# https://developers.google.com/google-ads/api/data/codes-formats
_LOCALE_TARGETS: dict[str, tuple[str, str]] = {
    "en": ("languageConstants/1000", "geoTargetConstants/2840"),  # English, United States
    "en-gb": ("languageConstants/1000", "geoTargetConstants/2826"),  # English, United Kingdom
    "en-us": ("languageConstants/1000", "geoTargetConstants/2840"),
    "tr": ("languageConstants/1037", "geoTargetConstants/2792"),  # Turkish, Turkey
    "de": ("languageConstants/1001", "geoTargetConstants/2276"),  # German, Germany
    "fr": ("languageConstants/1002", "geoTargetConstants/2250"),  # French, France
}


def ads_language_and_geo_for_locale(locale: str) -> tuple[str, str]:
    """Return (language_resource, geo_resource) for Keyword Planning requests."""
    key = (locale or "en").strip().lower().replace("_", "-")
    if key in _LOCALE_TARGETS:
        return _LOCALE_TARGETS[key]
    base = key.split("-", 1)[0]
    return _LOCALE_TARGETS.get(base, _LOCALE_TARGETS["en"])
