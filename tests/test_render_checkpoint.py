from pathlib import Path

import yaml
from typer.testing import CliRunner

from runlens.cli import app
from runlens.renderer import render_working_report
from runlens.store import ARTIFACTS_DIR, init_artifacts


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
    runner.invoke(app, ["init"])

    result = runner.invoke(app, ["render"])

    assert result.exit_code == 0
    assert (isolated_cwd / ARTIFACTS_DIR / "working" / "report.html").exists()
    assert not (isolated_cwd / ARTIFACTS_DIR / "deliverables" / "final.html").exists()
