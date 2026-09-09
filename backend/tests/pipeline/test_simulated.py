from __future__ import annotations

from app.config import DEFAULT_GEO_LLM_MODELS, Settings
from app.pipeline.scoring import geo_score
from app.pipeline.simulated import build_system_prompt, run_simulated_audit, run_simulated_audits
from app.providers.registry import get_openrouter_models


def test_system_prompt_uses_sector_not_fintech_lock():
    prompt = build_system_prompt("Defense Technology")
    assert '"sector": "Defense Technology"' in prompt
    assert '"sector": "fintech"' not in prompt


def test_dry_run_simulated_audit():
    record = run_simulated_audit(
        brand="Yanki Demo Co",
        prompt="Best analytics tools",
        prompt_group="recommendation",
        owned_domains=["yankidemoco.example"],
        aliases=["Yanki"],
        sector="Software",
        dry_run=True,
    )
    assert record["error"] is False
    assert record["measurement_mode"] == "simulated"
    assert record["mentioned"] is True
    assert record["sector"] == "Software"
    assert "citation_metrics" in record
    assert geo_score([record]) > 0


def test_dry_run_simulated_audits_fan_out_per_model():
    settings = Settings(dry_run=True)
    slugs = get_openrouter_models(settings)
    assert len(slugs) == len(DEFAULT_GEO_LLM_MODELS.split(","))

    records = run_simulated_audits(
        brand="Yanki Demo Co",
        prompt="Best analytics tools",
        prompt_group="recommendation",
        owned_domains=["yankidemoco.example"],
        dry_run=True,
        model_slugs=slugs,
    )

    assert len(records) == len(slugs)
    assert {record["model"] for record in records} == set(slugs)
    assert all(record["measurement_mode"] == "simulated" for record in records)
    assert all(record["error"] is False for record in records)


def test_simulated_audits_fail_open_across_models():
    class _ExplodingLLM:
        model = "stub/broken"

        def chat(self, messages, **kwargs):
            raise RuntimeError("upstream 500")

    class _WorkingLLM:
        model = "stub/ok"

        def chat(self, messages, **kwargs):
            from app.providers.base import ProviderResult

            return ProviderResult(
                text='{"simulated_answer": "Acme leads.", "citations": []}',
                model=self.model,
                cost_usd=0.002,
            )

    def llm_factory(slug: str):
        return _ExplodingLLM() if slug == "stub/broken" else _WorkingLLM()

    records = run_simulated_audits(
        brand="Acme",
        prompt="Best widgets",
        prompt_group="recommendation",
        owned_domains=["acme.example"],
        dry_run=False,
        model_slugs=["stub/broken", "stub/ok"],
        llm_factory=llm_factory,
    )

    assert len(records) == 2
    by_model = {record["model"]: record for record in records}
    assert by_model["stub/broken"]["error"] is True
    assert by_model["stub/ok"]["error"] is False
    assert by_model["stub/ok"]["_cost_usd"] == 0.002
