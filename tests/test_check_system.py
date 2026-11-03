"""Tests for scripts/check_system.sh (no Ollama service required)."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CHECK = ROOT / "scripts" / "check_system.sh"


@pytest.fixture(scope="module")
def check_script() -> Path:
    assert CHECK.is_file(), f"missing {CHECK}"
    return CHECK


def _run_check(script: Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    merged = os.environ.copy()
    if env:
        merged.update(env)
    return subprocess.run(
        ["bash", str(script)],
        cwd=str(ROOT),
        env=merged,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )


def test_check_system_runs_without_ollama_service(check_script: Path) -> None:
    result = _run_check(check_script)
    assert result.returncode == 0, result.stderr
    out = result.stdout
    assert "FoodCalories System Check" in out
    assert "Hardware assessment:" in out
    assert "AI model:" in out
    assert "Ollama:" in out
    # Must not crash when Ollama is stopped; exit stays 0.
    assert "Total RAM:" in out


def test_check_system_mentions_configured_model(check_script: Path) -> None:
    result = _run_check(check_script, env={"OLLAMA_MODEL": "demo-model:tag"})
    assert result.returncode == 0, result.stderr
    assert "demo-model:tag" in result.stdout


def test_check_system_assessment_values(check_script: Path) -> None:
    result = _run_check(check_script)
    assert result.returncode == 0, result.stderr
    # One of the documented assessment labels must appear.
    assert any(
        label in result.stdout
        for label in ("OK", "LIMITED", "UNSUITABLE", "UNKNOWN")
    )


def test_lab_message_when_assessment_limited_or_unsuitable(check_script: Path) -> None:
    """On constrained hosts the script should point students to laboratory PCs."""
    result = _run_check(check_script)
    assert result.returncode == 0, result.stderr
    if "Hardware assessment: LIMITED" in result.stdout or "Hardware assessment: UNSUITABLE" in result.stdout:
        assert "PolyU laboratory PC" in result.stdout


def test_setup_sh_skip_model_still_executable() -> None:
    setup = ROOT / "setup.sh"
    assert setup.is_file()
    # Syntax check only — do not run full setup in unit tests.
    result = subprocess.run(
        ["bash", "-n", str(setup)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_run_sh_syntax() -> None:
    run = ROOT / "run.sh"
    assert run.is_file()
    result = subprocess.run(
        ["bash", "-n", str(run)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
