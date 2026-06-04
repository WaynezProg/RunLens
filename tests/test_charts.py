"""v0.4 chart foundation: Vega-Lite spec -> inline SVG with table/link fallback.

The agent never hand-writes chart HTML. It drops a `.vl.json` spec on disk and
references it from `charts[]`; the renderer pre-renders it to SVG via vl-convert,
and falls back to a data table / link when the spec is missing or invalid. The
finalize gate must stay blind to charts (it only reads acceptance_criteria).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from runlens.charts import RenderedChart, render_chart
from runlens.cli import app
from runlens.models import MetadataItem
from runlens.renderer import render_working_report
from runlens.store import ARTIFACTS_DIR, init_artifacts, load_spec, write_spec

REPO_ROOT = Path(__file__).resolve().parents[1]
CHART_FIXTURES = REPO_ROOT / "examples" / "charts"


def _install(base: Path, name: str) -> str:
    rel = f"{ARTIFACTS_DIR}/working/charts/{name}"
    dst = base / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text((CHART_FIXTURES / name).read_text(encoding="utf-8"), encoding="utf-8")
    return rel


def _chart(path: str, title: str = "Chart") -> MetadataItem:
    return MetadataItem(path=path, type="vega-lite", title=title, status="ready")


@pytest.mark.parametrize("name", ["bar.vl.json", "line.vl.json"])
def test_valid_spec_renders_inline_svg(tmp_path: Path, name: str) -> None:
    rendered = render_chart(tmp_path, _chart(_install(tmp_path, name)))
    assert isinstance(rendered, RenderedChart)
    assert rendered.svg is not None
    assert rendered.svg.lstrip().startswith("<svg")
    assert rendered.fallback_reason is None


def test_invalid_spec_falls_back_to_table_without_raising(tmp_path: Path) -> None:
    rendered = render_chart(tmp_path, _chart(_install(tmp_path, "invalid.vl.json")))
    assert rendered.svg is None
    assert rendered.fallback_reason
    # invalid.vl.json carries inline data.values -> table fallback
    assert rendered.table_headers and rendered.table_rows


def test_missing_spec_file_falls_back_to_link(tmp_path: Path) -> None:
    rendered = render_chart(
        tmp_path, _chart(f"{ARTIFACTS_DIR}/working/charts/missing.vl.json")
    )
    assert rendered.svg is None
    assert "not found" in rendered.fallback_reason.lower()


def test_report_embeds_chart_svg(isolated_cwd: Path) -> None:
    init_artifacts(isolated_cwd)
    rel = _install(isolated_cwd, "bar.vl.json")
    spec = load_spec(isolated_cwd).model_copy(update={"charts": [_chart(rel, "Bar")]})
    write_spec(isolated_cwd, spec)

    html = render_working_report(isolated_cwd).read_text()
    assert "<svg" in html


def test_render_does_not_crash_on_invalid_chart(isolated_cwd: Path) -> None:
    init_artifacts(isolated_cwd)
    rel = _install(isolated_cwd, "invalid.vl.json")
    spec = load_spec(isolated_cwd).model_copy(update={"charts": [_chart(rel, "Broken")]})
    write_spec(isolated_cwd, spec)

    html = render_working_report(isolated_cwd).read_text()
    assert "<svg" not in html
    assert rel in html  # path still surfaced as a link/metadata


def test_finalize_gate_ignores_charts(isolated_cwd: Path) -> None:
    runner = CliRunner()
    assert runner.invoke(app, ["init"]).exit_code == 0
    rel = _install(isolated_cwd, "invalid.vl.json")
    spec = load_spec(isolated_cwd).model_copy(update={"charts": [_chart(rel, "Broken")]})
    write_spec(isolated_cwd, spec)
    assert (
        runner.invoke(
            app, ["criteria", "pass", "--id", "define-criteria", "--evidence", "ok"]
        ).exit_code
        == 0
    )

    result = runner.invoke(app, ["finalize"])

    assert result.exit_code == 0, result.output
    assert (isolated_cwd / ARTIFACTS_DIR / "deliverables" / "final.html").exists()
