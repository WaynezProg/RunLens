from pathlib import Path

from runlens.cli import app as cli_app
from typer.testing import CliRunner


def test_watch_requires_init(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        cli_app, ["watch", "--debounce", "0.1", "--poll-interval", "0.05"]
    )
    assert result.exit_code != 0
    assert "init" in result.stderr.lower() or "init" in result.stdout.lower()


def test_watch_help_lists_options():
    runner = CliRunner()
    result = runner.invoke(cli_app, ["watch", "--help"])
    assert result.exit_code == 0
    assert "--debounce" in result.stdout
    assert "--poll-interval" in result.stdout
