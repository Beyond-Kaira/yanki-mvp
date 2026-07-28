from __future__ import annotations

import json

import pytest

from app.pipeline.errors import PipelineError
from app.pipeline.kyc import KYC, build_prompt, generate_kyc, require_usable
from app.providers.base import ProviderResult


def test_prompt_forbids_guessing_and_keeps_mock_coupling():
    prompt = build_prompt("some site text", "https://x.com")
    # Anti-hallucination instruction is present.
    assert "Use ONLY facts stated in the website text" in prompt
    assert "Do NOT guess" in prompt
    # The mock provider keys off this substring (case-insensitive) - keep it.
    assert "json object" in prompt.lower()


class _CannedProvider:
    """A provider that returns a fixed string, ignoring the prompt."""

    name = "canned"
    model = "canned"

    def __init__(self, text: str) -> None:
        self._text = text

    def generate(self, prompt: str) -> ProviderResult:
        return ProviderResult(text=self._text, model=self.model, cost_usd=0.0)


def test_parses_fenced_json_and_validates():
    raw = (
        "```json\n"
        '{"company": "Globex", "description": "Widgets", "industry": "Manufacturing",'
        ' "aliases": ["Globex Corp"], "products": ["Widget"]}\n'
        "```"
    )
    kyc = generate_kyc("site text", "https://globex.com", _CannedProvider(raw))
    assert isinstance(kyc, KYC)
    assert kyc.company == "Globex"
    assert kyc.industry == "Manufacturing"


def test_aliases_always_include_company_and_domain():
    raw = '{"company": "Globex", "description": "d", "industry": "i"}'
    kyc = generate_kyc("text", "https://www.globex.co.uk/about", _CannedProvider(raw))
    lowered = [alias.lower() for alias in kyc.aliases]
    assert "globex" in lowered  # company name (and registrable domain name)


def test_domain_alias_skips_multipart_public_suffix():
    # For a multi-label ccTLD the registrable label is the brand, not the public
    # suffix segment: .co.uk -> "globex" (never "co"), .com.tr -> "sirket"
    # (never "com"). A short "co"/"com" alias would otherwise match inside
    # "companies"/"compare" and wrongly inflate the footprint score.
    raw = '{"company": "Globex", "description": "d", "industry": "i"}'
    couk = generate_kyc("text", "https://www.globex.co.uk/about", _CannedProvider(raw))
    couk_aliases = [alias.lower() for alias in couk.aliases]
    assert "globex" in couk_aliases
    assert "co" not in couk_aliases

    raw2 = '{"company": "Sirket", "description": "d", "industry": "i"}'
    comtr = generate_kyc("text", "https://sirket.com.tr", _CannedProvider(raw2))
    comtr_aliases = [alias.lower() for alias in comtr.aliases]
    assert "sirket" in comtr_aliases
    assert "com" not in comtr_aliases


def test_legal_suffix_stripped_form_is_added_as_an_alias():
    # Answers name the company the way people write it, not the way it is
    # registered. The registered name is kept too — this only ever adds.
    raw = '{"company": "Globex Robotics A.\\u015e.", "description": "d"}'
    kyc = generate_kyc("text", "https://globex.com", _CannedProvider(raw))
    lowered = [alias.lower() for alias in kyc.aliases]
    assert "globex robotics a.ş." in lowered
    assert "globex robotics" in lowered


@pytest.mark.parametrize(
    ("company", "expected_stem"),
    [
        ("Globex Robotics A.Ş.", "Globex Robotics"),
        ("Globex Robotics Ltd. Şti.", "Globex Robotics"),
        ("Globex, Inc.", "Globex"),
        ("Globex GmbH", "Globex"),
        ("Globex Limited", "Globex"),
    ],
)
def test_legal_suffix_stems(company, expected_stem):
    raw = json.dumps({"company": company, "description": "d"})
    kyc = generate_kyc("text", "https://globex.com", _CannedProvider(raw))
    assert expected_stem in kyc.aliases


@pytest.mark.parametrize("company", ["Zinc", "Sparc", "Inc", "Corporation"])
def test_legal_suffix_strip_needs_a_word_boundary(company):
    # "Zinc" is a brand, not "Z" + "inc"; a bare legal form has no stem at all.
    # Only the company itself and the registrable domain survive — no stem.
    raw = json.dumps({"company": company, "description": "d"})
    kyc = generate_kyc("text", "https://example.com", _CannedProvider(raw))
    assert kyc.aliases == [company, "example"]


def test_ascii_folded_company_is_added_as_an_alias():
    # checker_summary excludes competitors by casefold alone, so the folded form
    # has to exist as a real alias for "Turk Holding" to be suppressed.
    raw = '{"company": "T\\u00fcrk Holding", "description": "d"}'
    kyc = generate_kyc("text", "https://example.com", _CannedProvider(raw))
    assert "Türk Holding" in kyc.aliases
    assert "Turk Holding" in kyc.aliases


def test_plain_ascii_company_gains_no_duplicate_aliases():
    # The extra forms are added only when they differ — the alias chips a user
    # sees must not fill up with copies of the same name.
    raw = '{"company": "Globex", "description": "d"}'
    kyc = generate_kyc("text", "https://globex.com", _CannedProvider(raw))
    assert kyc.aliases == ["Globex"]


def test_cctld_fills_empty_location():
    # A two-level suffix (.com.tr) still resolves to the ccTLD "tr" -> Türkiye.
    raw = '{"company": "Beyond", "description": "d", "industry": "i"}'
    kyc = generate_kyc("text", "https://example.com.tr", _CannedProvider(raw))
    assert kyc.locations == ["Türkiye"]

    de = generate_kyc("text", "https://example.de", _CannedProvider(raw))
    assert de.locations == ["Germany"]


def test_cctld_does_not_fire_for_generic_tld():
    raw = '{"company": "Beyond", "description": "d", "industry": "i"}'
    kyc = generate_kyc("text", "https://example.com", _CannedProvider(raw))
    assert kyc.locations == []


def test_cctld_never_overrides_reported_location():
    raw = (
        '{"company": "Beyond", "description": "d", "industry": "i",'
        ' "locations": ["Ankara"]}'
    )
    kyc = generate_kyc("text", "https://example.de", _CannedProvider(raw))
    assert kyc.locations == ["Ankara"]


def test_invalid_json_raises_pipeline_error():
    with pytest.raises(PipelineError):
        generate_kyc("text", "https://x.com", _CannedProvider("not json at all"))


def test_missing_required_field_raises_pipeline_error():
    # No "company" field -> validation failure -> PipelineError.
    raw = '{"description": "d", "industry": "i"}'
    with pytest.raises(PipelineError):
        generate_kyc("text", "https://x.com", _CannedProvider(raw))


def test_require_usable_accepts_a_thin_but_legitimate_profile():
    # The gate rejects *useless*, never merely thin: one keyword is enough.
    require_usable(KYC(company="Globex", keywords=["widgets"]))
    require_usable(KYC(company="Globex", services=["consulting"]))
    require_usable(KYC(company="Globex", industry="Manufacturing"))


def test_require_usable_rejects_an_empty_company():
    # company has no min_length, so this validates — and then footprint has
    # nothing to match and scores every answer against an empty brand.
    with pytest.raises(PipelineError, match="company"):
        require_usable(KYC(company="", keywords=["widgets"]))
    with pytest.raises(PipelineError, match="company"):
        require_usable(KYC(company="   ", keywords=["widgets"]))


def test_require_usable_rejects_a_profile_with_no_topic_signal():
    # No keyword/service/industry -> the topic pool falls back to the literal
    # "solutions" and we would pay to ask generic questions about "solutions".
    with pytest.raises(PipelineError, match="does"):
        require_usable(KYC(company="Globex"))


def test_require_usable_accepts_a_caller_supplied_topic():
    # The checker's submitted category is real input even when the model does
    # not echo it back into keywords/services/industry.
    require_usable(KYC(company="Nike"), known_topic="running shoes")
    with pytest.raises(PipelineError):
        require_usable(KYC(company="Nike"), known_topic="   ")


class _ScriptedProvider:
    """Returns each queued response in turn, so a retry can differ from the first."""

    name = "scripted"
    model = "scripted"

    def __init__(self, *responses: str) -> None:
        self._responses = list(responses)
        self.prompts: list[str] = []

    def generate(self, prompt: str) -> ProviderResult:
        self.prompts.append(prompt)
        index = min(len(self.prompts) - 1, len(self._responses) - 1)
        return ProviderResult(
            text=self._responses[index], model=self.model, cost_usd=0.0
        )


_VALID = '{"company": "Globex", "description": "Widgets", "industry": "Manufacturing"}'


def test_prose_wrapped_json_is_repaired_without_a_retry():
    # The repair is a string operation, so a formatting slip costs $0 and one
    # call — not a second round trip.
    provider = _ScriptedProvider(f"Here is the profile:\n{_VALID}\nHope this helps!")
    kyc = generate_kyc("text", "https://globex.com", provider)
    assert kyc.company == "Globex"
    assert len(provider.prompts) == 1


def test_unusable_first_response_is_retried_once():
    provider = _ScriptedProvider("I'm sorry, I can't help with that.", _VALID)
    kyc = generate_kyc("text", "https://globex.com", provider)
    assert kyc.company == "Globex"
    assert len(provider.prompts) == 2


def test_retry_is_bounded_at_one_and_then_raises():
    provider = _ScriptedProvider("nope", "still nope")
    with pytest.raises(PipelineError):
        generate_kyc("text", "https://globex.com", provider)
    assert len(provider.prompts) == 2  # one attempt + one retry, never a loop


def test_happy_path_still_costs_exactly_one_call():
    provider = _ScriptedProvider(_VALID)
    generate_kyc("text", "https://globex.com", provider)
    assert len(provider.prompts) == 1


def test_retry_resends_the_prompt_the_mock_provider_keys_off():
    # MockProvider returns its canned profile only when the prompt contains
    # "json object" (mock.py:46-50). If the retry ever stops re-sending the same
    # prompt, DRY_RUN and the e2e break — so pin it here.
    provider = _ScriptedProvider("nope", _VALID)
    generate_kyc("text", "https://globex.com", provider)
    assert len(provider.prompts) == 2
    assert provider.prompts[0] == provider.prompts[1]
    assert all("json object" in prompt.lower() for prompt in provider.prompts)


def test_validation_failure_keeps_its_own_message():
    # Well-formed JSON of the wrong shape is a different failure from
    # unparseable text, and the user-facing wording still says so.
    raw = '{"description": "d"}'  # parses, but has no company
    with pytest.raises(PipelineError, match="incomplete"):
        generate_kyc("text", "https://x.com", _CannedProvider(raw))
    with pytest.raises(PipelineError, match="could not read"):
        generate_kyc("text", "https://x.com", _CannedProvider("not json at all"))
