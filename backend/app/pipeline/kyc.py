"""Step 2 - KYC: turn discovered site text into a structured company profile.

Makes one LLM call asking for strict JSON, parses it tolerantly (stripping any
```json fences, then falling back to the outermost ``{ ... }`` span so a stray
"Here is the profile:" prefix costs nothing), and validates against the ``KYC``
model. If that still yields nothing usable it retries **once** before failing —
discovery is already paid for by then, so a formatting slip should not burn the
whole job. Aliases always include
the company name and the registrable domain name (without TLD) so footprint
detection has something to match on, plus — when they differ from what is
already there — the ASCII-folded and legal-suffix-stripped forms of the company
name, because an answer says "Globex Robotics", not "Globex Robotics A.Ş.".

When the model reports no locations, we fall back to the country implied by the
URL's country-code TLD (``.com.tr`` -> Türkiye, ``.de`` -> Germany, ...). That
is a fact about the domain, not a guess about the text, so prompts can still ask
"in Türkiye" instead of "worldwide". A non-empty ``locations`` is never
overridden, and the JSON contract/fields are unchanged.
"""

from __future__ import annotations

import json
from urllib.parse import urlparse

from pydantic import BaseModel, Field, ValidationError

from app.pipeline.errors import PipelineError
from app.pipeline.textfold import fold_ascii


class KYC(BaseModel):
    company: str
    description: str = ""
    industry: str = ""
    aliases: list[str] = Field(default_factory=list)
    products: list[str] = Field(default_factory=list)
    services: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=list)
    competitors: list[str] = Field(default_factory=list)


_PROMPT = """You are analysing a company from its website text.

Return a single JSON object describing the company, with these fields:
company (string), description (string), industry (string),
aliases (array of strings), products (array of strings),
services (array of strings), keywords (array of strings),
locations (array of strings), competitors (array of strings).

Rules:
- Use ONLY facts stated in the website text. Do NOT guess, infer, or invent
  anything. Prefer an empty string or empty array over a guess.
- Extract SPECIFIC product and model names exactly as written (the actual
  product or model name, never a generic category).
- If the text is in another language (for example Turkish), still write the
  fields in English, but keep proper nouns and product/model names verbatim.
- List competitors ONLY if they are literally named in the text.

Respond with ONLY the JSON object - no prose, no markdown fences.

Website URL: {url}
Website text:
{text}
"""


def build_prompt(text: str, url: str) -> str:
    return _PROMPT.format(url=url, text=text)


def _strip_fences(raw: str) -> str:
    stripped = raw.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip().startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()


# Second-level labels that are part of a public suffix, not a registrable name
# (e.g. the "co" in example.co.uk, the "com" in example.com.tr). When one of
# these is the second-to-last label we skip it, so ".co.uk"/".com.tr" domains
# yield the real brand (e.g. "globex") rather than a garbage "co"/"com" alias.
_SECOND_LEVEL_SUFFIXES = {"co", "com", "org", "net", "gov", "edu", "ac", "gob", "mil"}


def _registrable_name(url: str) -> str:
    parsed = urlparse(url)
    host = parsed.netloc or parsed.path
    host = host.split("@")[-1].split(":")[0]
    if host.startswith("www."):
        host = host[4:]
    labels = [label for label in host.split(".") if label]
    if len(labels) >= 3 and labels[-2] in _SECOND_LEVEL_SUFFIXES:
        return labels[-3]
    if len(labels) >= 2:
        return labels[-2]
    return labels[0] if labels else ""


# Country-code TLDs we map to a country name for the location fallback. The
# ccTLD is always the final label, so two-level suffixes (com.tr, co.uk) are
# handled for free by looking at that last label.
_CCTLD_COUNTRIES = {
    "tr": "Türkiye",
    "de": "Germany",
    "fr": "France",
    "it": "Italy",
    "es": "Spain",
    "nl": "Netherlands",
    "uk": "United Kingdom",
    "us": "United States",
    "sa": "Saudi Arabia",
    "ae": "United Arab Emirates",
}


def _cctld_country(url: str) -> str:
    """Country name implied by the URL's country-code TLD, or "" if none."""
    parsed = urlparse(url)
    host = parsed.netloc or parsed.path
    host = host.split("@")[-1].split(":")[0]
    labels = [label for label in host.split(".") if label]
    if not labels:
        return ""
    return _CCTLD_COUNTRIES.get(labels[-1].lower(), "")


# Legal-form suffixes that belong to a *registered* name but almost never to the
# way an answer refers to the company ("Globex Robotics A.Ş." is written "Globex
# Robotics"). Matched longest-first so "Ltd. Şti." wins over "Ltd.".
_LEGAL_SUFFIXES = sorted(
    (
        "anonim şirketi",
        "ltd. şti.",
        "ltd şti.",
        "ltd şti",
        "corporation",
        "limited",
        "a.ş.",
        "a.ş",
        "a.s.",
        "s.r.l.",
        "gmbh",
        "sarl",
        "corp.",
        "corp",
        "inc.",
        "inc",
        "llc",
        "plc",
        "s.a.",
        "b.v.",
        "n.v.",
    ),
    key=len,
    reverse=True,
)

# A stripped stem shorter than this is noise, not a brand.
_MIN_ALIAS_LEN = 2

# Characters that may sit between a name and its legal suffix.
_SUFFIX_BOUNDARY = " .,-"


def _strip_legal_suffix(name: str) -> str:
    """``"Globex Robotics A.Ş."`` -> ``"Globex Robotics"``; ``""`` if nothing to strip.

    This only ever produces an *extra* alias — the registered name itself is
    never removed or rewritten.
    """
    lowered = name.casefold()
    for suffix in _LEGAL_SUFFIXES:
        if not lowered.endswith(suffix):
            continue
        cut = len(name) - len(suffix)
        # Require a real boundary before the suffix, or "Zinc" reads as "Z" +
        # "inc" and "Sparc" as "Spa" + "rc".
        if cut <= 0 or name[cut - 1] not in _SUFFIX_BOUNDARY:
            continue
        stem = name[:cut].rstrip(_SUFFIX_BOUNDARY)
        if len(stem) >= _MIN_ALIAS_LEN:
            return stem
    return ""


def _ensure_alias(kyc: KYC, value: str) -> None:
    value = (value or "").strip()
    if value and value.lower() not in [alias.lower() for alias in kyc.aliases]:
        kyc.aliases.append(value)


def _ensure_name_aliases(kyc: KYC, name: str) -> None:
    """Add a company name plus the other forms an answer is likely to use.

    Two extras, each added only when it actually differs from what is already
    there (so an ASCII, suffix-free brand gains nothing and the alias chips the
    user sees stay clean):

    * the ASCII-folded form — ``footprint`` folds both sides itself, but
      ``checker_summary`` excludes competitors by casefold alone, so ``Türk
      Holding`` would otherwise fail to suppress a reported ``Turk Holding``;
    * the legal-suffix-stripped stem, which is how people actually write it.
    """
    name = (name or "").strip()
    if not name:
        return
    _ensure_alias(kyc, name)
    _ensure_alias(kyc, fold_ascii(name))
    stem = _strip_legal_suffix(name)
    if stem:
        _ensure_alias(kyc, stem)
        _ensure_alias(kyc, fold_ascii(stem))


_UNREADABLE = "could not read the company profile"
_INCOMPLETE = "the company profile was incomplete"


def _outermost_object(payload: str) -> str:
    """The outermost ``{ ... }`` span, or ``""`` if there is none.

    A model that opens with "Here is the profile:" still emitted valid JSON — it
    just wrapped it in prose. Recovering that span is free and needs no network.
    """
    start = payload.find("{")
    end = payload.rfind("}")
    if start == -1 or end <= start:
        return ""
    return payload[start : end + 1]


def _candidates(raw: str) -> list[str]:
    """Payloads worth trying for one response, cheapest first."""
    stripped = _strip_fences(raw)
    span = _outermost_object(stripped)
    return [stripped] if span in ("", stripped) else [stripped, span]


def _read_profile(raw: str) -> tuple[KYC | None, str]:
    """``(kyc, "")`` on success, else ``(None, message)`` naming the failure."""
    reason = _UNREADABLE
    for candidate in _candidates(raw):
        try:
            data = json.loads(candidate)
        except (json.JSONDecodeError, ValueError):
            continue
        if not isinstance(data, dict):
            continue
        try:
            return KYC(**data), ""
        except ValidationError:
            # Well-formed JSON of the wrong shape is a different failure to
            # unparseable text, and the user-facing message says so.
            reason = _INCOMPLETE
    return None, reason


def require_usable(kyc: KYC, known_topic: str = "") -> None:
    """Raise ``PipelineError`` if this profile is not worth paying to fan out on.

    Two ways a validated profile is still useless:

    * ``company`` has no ``min_length``, so ``company=""`` passes validation.
      ``_ensure_name_aliases`` then silently no-ops and ``footprint`` has nothing
      to match, scoring every answer against an empty brand.
    * With no keyword, service or industry signal, the topic pool falls back to
      the literal ``"solutions"`` and we spend the run asking generic questions
      about "solutions".

    Either way the job goes on to ``execute`` — the single most expensive step in
    the pipeline, up to ``max_responses_per_job`` (default 60) paid calls — and
    returns a plausible-looking GEO score that is quietly meaningless.

    ``known_topic`` lets a caller contribute a topic signal it already trusts:
    the checker's submitted category is real input even when the model does not
    echo it back into keywords/services/industry.
    """
    if not (kyc.company or "").strip():
        raise PipelineError("could not identify the company — nothing to measure")
    signals = [*kyc.keywords, *kyc.services, kyc.industry, known_topic]
    if not any((signal or "").strip() for signal in signals):
        raise PipelineError("could not identify what the company does")


def generate_kyc(text: str, url: str, provider) -> KYC:
    prompt = build_prompt(text, url)
    kyc, reason = _read_profile(provider.generate(prompt).text)
    if kyc is None:
        # Discovery has already been paid for by the time we get here, so one
        # stray prose prefix must not burn the whole job. The repair above costs
        # nothing; this is the single bounded retry, and it deliberately re-sends
        # the SAME prompt: MockProvider only returns its canned profile because
        # the prompt contains "json object", so a different repair prompt would
        # have to keep that phrase or break DRY_RUN and the e2e in lockstep.
        kyc, reason = _read_profile(provider.generate(prompt).text)
    if kyc is None:
        raise PipelineError(reason)

    _ensure_name_aliases(kyc, kyc.company)
    _ensure_alias(kyc, _registrable_name(url))

    # Deterministic location fallback from the domain's ccTLD (never overrides a
    # location the model actually found).
    if not kyc.locations:
        country = _cctld_country(url)
        if country:
            kyc.locations = [country]

    return kyc
