"""Tests for the AgentPolicy CLI."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from agentpolicy.cli import main


EXAMPLE_POLICY = Path(__file__).resolve().parents[1] / "examples" / "policy.yaml"


def test_cli_validate(capsys, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["agentpolicy", "validate", str(EXAMPLE_POLICY)])
    assert main() == 0
    captured = capsys.readouterr()
    assert "Policy valid" in captured.out


def test_cli_explain(capsys, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["agentpolicy", "explain", str(EXAMPLE_POLICY)])
    assert main() == 0
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["budget"] == 5.0
    assert "check_tool" in payload["supported_checks"]


def test_cli_demo(capsys, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["agentpolicy", "demo", str(EXAMPLE_POLICY)])
    assert main() == 0
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["session_id"] == "pol_demo"
    assert payload["decision_summary"]["allow"] >= 2


def test_cli_module_execution(capsys, monkeypatch):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
    result = subprocess.run(
        [sys.executable, "-m", "agentpolicy.cli", "validate", str(EXAMPLE_POLICY)],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0
    assert "Policy valid" in result.stdout
