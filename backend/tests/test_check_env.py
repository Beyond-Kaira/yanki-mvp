"""Tests for scripts/check_env.py — the deploy preflight key check.

The script is the gate deploy.sh runs before a live release; these lock in the
contract the deploy driver depends on: DRY_RUN needs zero keys, and a live
(DRY_RUN=0) deploy fails loudly naming exactly the variable(s) the measured path
needs. Driven as a subprocess with a clean environment so the outer test env
cannot leak keys or DRY_RUN into the check.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check_env.py"

# JWT + OpenRouter are needed on every live deploy; Tavily only in measured mode.
LIVE_MEASURED = (
    "DRY_RUN=0\n"
    "GEO_MODE=measured\n"
    "JWT_SECRET_KEY=jwt-xxx\n"
    "OPEN_ROUTER_KEY=or-xxx\n"
    "TAVILY_API_KEY=tv-xxx\n"
)


def run(tmp_path: Path, contents: str) -> subprocess.CompletedProcess[str]:
    env_file = tmp_path / "test.env"
    env_file.write_text(contents)
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(env_file)],
        capture_output=True,
        text=True,
        env={"PATH": os.environ.get("PATH", "")},  # clean env: no leaked keys
    )


def test_dry_run_no_keys_passes(tmp_path):
    proc = run(tmp_path, "DRY_RUN=1\n")
    assert proc.returncode == 0, proc.stderr
    assert "no API keys required" in proc.stdout


def test_absent_dry_run_defaults_to_dry_and_passes(tmp_path):
    # `make dev` / `make test` ship no keys and no DRY_RUN; must stay silent.
    proc = run(tmp_path, "# nothing here\n")
    assert proc.returncode == 0, proc.stderr


def test_live_measured_all_keys_passes(tmp_path):
    proc = run(tmp_path, LIVE_MEASURED)
    assert proc.returncode == 0, proc.stderr
    assert "looks complete" in proc.stdout


def test_live_missing_tavily_fails_and_names_it(tmp_path):
    contents = LIVE_MEASURED.replace("TAVILY_API_KEY=tv-xxx\n", "TAVILY_API_KEY=\n")
    proc = run(tmp_path, contents)
    assert proc.returncode == 1
    assert "TAVILY_API_KEY" in proc.stderr
    assert "measured" in proc.stderr.lower()


def test_live_missing_openrouter_fails_and_names_it(tmp_path):
    contents = LIVE_MEASURED.replace("OPEN_ROUTER_KEY=or-xxx\n", "OPEN_ROUTER_KEY=\n")
    proc = run(tmp_path, contents)
    assert proc.returncode == 1
    assert "OPEN_ROUTER_KEY" in proc.stderr


def test_live_missing_jwt_fails_and_names_it(tmp_path):
    contents = LIVE_MEASURED.replace("JWT_SECRET_KEY=jwt-xxx\n", "JWT_SECRET_KEY=\n")
    proc = run(tmp_path, contents)
    assert proc.returncode == 1
    assert "JWT_SECRET_KEY" in proc.stderr


def test_live_default_geo_mode_requires_tavily(tmp_path):
    # GEO_MODE unset -> config default is "measured", so Tavily is still required.
    contents = "DRY_RUN=0\nJWT_SECRET_KEY=j\nOPEN_ROUTER_KEY=o\n"
    proc = run(tmp_path, contents)
    assert proc.returncode == 1
    assert "TAVILY_API_KEY" in proc.stderr


def test_simulated_mode_does_not_require_tavily(tmp_path):
    contents = "DRY_RUN=0\nGEO_MODE=simulated\nJWT_SECRET_KEY=j\nOPEN_ROUTER_KEY=o\n"
    proc = run(tmp_path, contents)
    assert proc.returncode == 0, proc.stderr


def test_retired_keys_are_not_required(tmp_path):
    # A live measured config with the real keys but NONE of the retired
    # four-engine keys must pass — checking them was the original bug.
    proc = run(tmp_path, LIVE_MEASURED)
    assert proc.returncode == 0, proc.stderr


def test_retired_keys_do_not_satisfy(tmp_path):
    # Setting only the retired keys must NOT make a live deploy pass.
    contents = "DRY_RUN=0\nGEO_MODE=measured\nANTHROPIC_API_KEY=a\nOPENAI_API_KEY=o\n"
    proc = run(tmp_path, contents)
    assert proc.returncode == 1
    # every genuinely-required var should be named
    for key in ("JWT_SECRET_KEY", "OPEN_ROUTER_KEY", "TAVILY_API_KEY"):
        assert key in proc.stderr
