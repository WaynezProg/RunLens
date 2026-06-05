"""Tests for `runlens hook` subcommand."""
import json
from pathlib import Path

from runlens.cli import app as cli_app
from typer.testing import CliRunner


def test_hook_writes_normalized_event(isolated_cwd: Path, monkeypatch, tmp_path: Path):
    """Hook command receives stdin JSON and appends normalized event to hooks.jsonl."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))

    payload = {"test_key": "test_value"}
    runner = CliRunner()
    cli_result = runner.invoke(
        cli_app,
        ["hook", "--event", "SessionStart", "--agent", "claude-code"],
        input=json.dumps(payload),
    )
    assert cli_result.exit_code == 0, f"stdout={cli_result.output}\nexception={cli_result.exception}"

    jsonl_file = tmp_path / "runlens" / "hooks.jsonl"
    assert jsonl_file.exists(), f"hooks.jsonl not found; tmp_path={list(tmp_path.iterdir())}"

    lines = jsonl_file.read_text().strip().splitlines()
    assert len(lines) == 1
    event = json.loads(lines[0])
    assert event["event"] == "SessionStart"
    assert event["agent"] == "claude-code"
    assert event["raw"] == payload
    assert "ts" in event


def test_hook_sanitizes_secrets(isolated_cwd: Path, monkeypatch, tmp_path: Path):
    """Secret fields (Authorization, api_key, token, etc.) are stripped from raw payload."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))

    payload = {
        "type": "PostToolUse",
        "tool": "Bash",
        "Authorization": "Bearer sk-12345",
        "api_key": "key-abc",
        "safe_field": "keep me",
        "headers": {"Authorization": "Bearer secret", "Content-Type": "application/json"},
    }
    runner = CliRunner()
    cli_result = runner.invoke(
        cli_app,
        ["hook", "--event", "PostToolUse", "--agent", "claude-code"],
        input=json.dumps(payload),
    )
    assert cli_result.exit_code == 0, cli_result.output

    jsonl_file = tmp_path / "runlens" / "hooks.jsonl"
    event = json.loads(jsonl_file.read_text().strip().splitlines()[0])
    raw = event["raw"]
    assert "Authorization" not in raw
    assert "api_key" not in raw
    assert raw["safe_field"] == "keep me"
    assert "Authorization" not in raw.get("headers", {})
    assert raw["headers"]["Content-Type"] == "application/json"


def test_hook_handles_empty_stdin(isolated_cwd: Path, monkeypatch, tmp_path: Path):
    """Hook command handles empty stdin gracefully (raw defaults to empty dict)."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))

    runner = CliRunner()
    cli_result = runner.invoke(
        cli_app,
        ["hook", "--event", "Stop", "--agent", "claude-code"],
        input="",
    )
    assert cli_result.exit_code == 0, cli_result.output

    jsonl_file = tmp_path / "runlens" / "hooks.jsonl"
    event = json.loads(jsonl_file.read_text().strip().splitlines()[0])
    assert event["event"] == "Stop"
    assert event["raw"] == {}


def test_hook_appends_without_overwriting(isolated_cwd: Path, monkeypatch, tmp_path: Path):
    """Multiple hook calls append to jsonl without overwriting prior events."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))

    runner = CliRunner()
    for i in range(3):
        cli_result = runner.invoke(
            cli_app,
            ["hook", "--event", f"Event{i}", "--agent", "claude-code"],
            input=json.dumps({"seq": i}),
        )
        assert cli_result.exit_code == 0, cli_result.output

    jsonl_file = tmp_path / "runlens" / "hooks.jsonl"
    lines = jsonl_file.read_text().strip().splitlines()
    assert len(lines) == 3
    events = [json.loads(line) for line in lines]
    assert [e["event"] for e in events] == ["Event0", "Event1", "Event2"]
    assert [e["raw"]["seq"] for e in events] == [0, 1, 2]
