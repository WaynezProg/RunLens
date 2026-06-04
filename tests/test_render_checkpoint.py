from pathlib import Path

import yaml
from typer.testing import CliRunner

from runlens.cli import app
from runlens.renderer import render_working_report
from runlens.store import ARTIFACTS_DIR, init_artifacts, load_state


def invoke_ok(runner: CliRunner, args: list[str]):
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    return result


def test_render_can_be_rerun_and_only_writes_working_report(isolated_cwd: Path):
    init_artifacts(isolated_cwd)

    first = render_working_report(isolated_cwd)
    second = render_working_report(isolated_cwd)

    assert first == isolated_cwd / ARTIFACTS_DIR / "working" / "report.html"
    assert second == first
    html = first.read_text()
    assert "RunLens task" in html
    assert "define-criteria" in html
    assert not (isolated_cwd / ARTIFACTS_DIR / "deliverables" / "final.html").exists()


def test_chart_metadata_passthrough_appears_as_table_fallback(isolated_cwd: Path):
    init_artifacts(isolated_cwd)
    spec_path = isolated_cwd / ARTIFACTS_DIR / "artifact_spec.yaml"
    spec = yaml.safe_load(spec_path.read_text())
    spec["charts"] = [
        {
            "path": "working/charts/chart_001.vl.json",
            "type": "vega-lite",
            "title": "Revenue trend",
            "status": "ready",
        }
    ]
    spec_path.write_text(yaml.safe_dump(spec, sort_keys=False))

    report = render_working_report(isolated_cwd)

    html = report.read_text()
    assert "Revenue trend" in html
    assert "working/charts/chart_001.vl.json" in html
    assert "Chart metadata" in html


def test_render_escapes_spec_fields(isolated_cwd: Path):
    init_artifacts(isolated_cwd)
    spec_path = isolated_cwd / ARTIFACTS_DIR / "artifact_spec.yaml"
    spec = yaml.safe_load(spec_path.read_text())
    spec["task"]["title"] = "<script>alert(1)</script>"
    spec_path.write_text(yaml.safe_dump(spec, sort_keys=False))

    report = render_working_report(isolated_cwd)

    html = report.read_text()
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html


def test_cli_render_writes_working_report_only(isolated_cwd: Path):
    runner = CliRunner()
    invoke_ok(runner, ["init"])

    result = runner.invoke(app, ["render"])

    assert result.exit_code == 0
    assert (isolated_cwd / ARTIFACTS_DIR / "working" / "report.html").exists()
    assert not (isolated_cwd / ARTIFACTS_DIR / "deliverables" / "final.html").exists()


def test_cli_render_before_init_exits_with_user_facing_error(isolated_cwd: Path):
    runner = CliRunner()

    result = runner.invoke(app, ["render"])

    assert result.exit_code != 0
    assert "Run runlens init first" in result.output
    assert "Traceback" not in result.output
    assert "FileNotFoundError" not in result.output


def test_checkpoint_command_creates_checkpoint_and_sets_state(isolated_cwd: Path):
    runner = CliRunner()
    init_result = runner.invoke(app, ["init"])
    assert init_result.exit_code == 0

    result = runner.invoke(app, ["checkpoint", "--reason", "tests not finished"])

    assert result.exit_code == 0
    checkpoints = list((isolated_cwd / ARTIFACTS_DIR / "checkpoints").glob("checkpoint-*.html"))
    assert len(checkpoints) == 1
    assert "tests not finished" in checkpoints[0].read_text()
    assert load_state(isolated_cwd).state == "checkpoint"
    assert load_state(isolated_cwd).note == "tests not finished"
