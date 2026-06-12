"""v0.3 adapter smoke tests.

The canonical RunLens workflow lives in `examples/smoke-fixture/run.sh` as the
single source of truth. These tests prove:

1. Running that sequence from an empty folder produces `deliverables/final.html`.
2. Every agent adapter (AGENTS.md / CLAUDE.md / opencode SKILL.md) documents the
   same canonical commands, so different agents are steered to one workflow.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from runlens.cli import app

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE = REPO_ROOT / "examples" / "smoke-fixture" / "run.sh"
README = REPO_ROOT / "README.md"
TRIGGER_MAP = REPO_ROOT / "docs" / "agent-trigger-map.md"
ADAPTERS = (
    REPO_ROOT / "AGENTS.md",
    REPO_ROOT / "CLAUDE.md",
    REPO_ROOT / "examples" / "adapters" / "runlens-artifact-protocol" / "SKILL.md",
    REPO_ROOT / "examples" / "adapters" / "opencode" / "runlens-artifact-protocol" / "SKILL.md",
)


def _runlens_invocations() -> list[list[str]]:
    """Parse `run.sh` into argv lists for each `runlens ...` command line."""
    commands: list[list[str]] = []
    for raw in FIXTURE.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        tokens = shlex.split(line)
        if tokens and tokens[0] == "runlens":
            commands.append(tokens[1:])
    return commands


def _canonical_signatures(invocations: list[list[str]]) -> set[str]:
    """Command signatures every adapter must teach (e.g. "init", "criteria pass")."""
    signatures: set[str] = set()
    for argv in invocations:
        positional = [tok for tok in argv if not tok.startswith("-")]
        if not positional:
            continue
        if positional[0] == "criteria" and len(positional) >= 2:
            signatures.add(f"criteria {positional[1]}")
        else:
            signatures.add(positional[0])
    return signatures


def _write_runlens_shim(bin_dir: Path) -> None:
    bin_dir.mkdir()
    shim = bin_dir / "runlens"
    src_path = REPO_ROOT / "src"
    shim.write_text(
        "\n".join(
            [
                "#!/usr/bin/env bash",
                "set -euo pipefail",
                f'export PYTHONPATH="{src_path}${{PYTHONPATH:+:$PYTHONPATH}}"',
                f'exec "{sys.executable}" -c \'from runlens.cli import app; app(prog_name="runlens")\' "$@"',
                "",
            ]
        ),
        encoding="utf-8",
    )
    shim.chmod(0o755)


def test_smoke_fixture_workflow_reaches_final(isolated_cwd: Path) -> None:
    runner = CliRunner()
    invocations = _runlens_invocations()
    assert invocations, "run.sh must contain runlens commands"

    for argv in invocations:
        result = runner.invoke(app, argv)
        assert result.exit_code == 0, f"`runlens {' '.join(argv)}` failed:\n{result.output}"

    final_html = isolated_cwd / ".agent-artifacts" / "deliverables" / "final.html"
    assert final_html.exists(), "canonical workflow must produce deliverables/final.html"

    state = json.loads(
        (isolated_cwd / ".agent-artifacts" / "run_state.json").read_text(encoding="utf-8")
    )
    assert state["state"] == "final"


def test_smoke_fixture_script_runs_from_empty_directory(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    _write_runlens_shim(bin_dir)
    env = {
        **os.environ,
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
    }

    result = subprocess.run(
        ["bash", str(FIXTURE)],
        cwd=empty_dir,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr + result.stdout
    assert (empty_dir / ".agent-artifacts" / "deliverables" / "final.html").exists()


@pytest.mark.parametrize("adapter", ADAPTERS, ids=lambda p: p.name)
def test_adapter_documents_canonical_commands(adapter: Path) -> None:
    text = adapter.read_text(encoding="utf-8").lower()
    # Word-boundary match so prose like "acceptance criteria passed" does not
    # masquerade as documenting the `criteria pass` command.
    missing = sorted(
        sig
        for sig in _canonical_signatures(_runlens_invocations())
        if not re.search(rf"{re.escape(sig.lower())}\b", text)
    )
    assert not missing, f"{adapter.name} does not document canonical commands: {missing}"


def test_readme_documents_agent_install_and_trigger_map() -> None:
    text = README.read_text(encoding="utf-8")
    for phrase in [
        "bash scripts/install-agent-hooks.sh",
        "docs/agent-trigger-map.md",
        "~/.codex/skills/runlens-artifact-protocol/SKILL.md",
        "When RunLens should trigger",
    ]:
        assert phrase in text


def test_trigger_map_documents_platform_specific_entrypoints() -> None:
    text = TRIGGER_MAP.read_text(encoding="utf-8")
    for phrase in [
        "Claude Code",
        "Codex",
        "OpenCode",
        "Cursor",
        "~/.claude/skills/runlens-artifact-protocol/SKILL.md",
        "~/.codex/skills/runlens-artifact-protocol/SKILL.md",
        "~/.config/opencode/skills/runlens-artifact-protocol/SKILL.md",
        "~/.cursor/skills/runlens-artifact-protocol/SKILL.md",
        "Stop hook",
        "runlens watch",
    ]:
        assert phrase in text
