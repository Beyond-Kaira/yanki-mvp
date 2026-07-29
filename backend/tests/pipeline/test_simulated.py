from __future__ import annotations

from app.pipeline.scoring import geo_score
from app.pipeline.simulated import build_system_prompt, run_simulated_audit


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
