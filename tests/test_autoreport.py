from pathlib import Path

from runlens.autoreport import emit_report_on_stop
from runlens.models import AcceptanceCriterion
from runlens.store import ARTIFACTS_DIR, init_artifacts, load_spec, load_state, write_spec


def _set_required(base: Path, *, status: str, evidence: str | None) -> None:
    spec = load_spec(base)
    spec.acceptance_criteria = [
        AcceptanceCriterion(
            id="done",
            description="Work complete",
            status=status,
            evidence=evidence,
            required=True,
        )
    ]
    write_spec(base, spec)


def test_no_artifacts_is_noop(tmp_path: Path):
    outcome = emit_report_on_stop(tmp_path)
    assert outcome.skipped_no_artifacts is True
    assert outcome.rendered is False
    assert not (tmp_path / ARTIFACTS_DIR).exists()


def test_renders_working_when_criteria_not_passed(tmp_path: Path):
    init_artifacts(tmp_path)  # seeds a pending required placeholder
    outcome = emit_report_on_stop(tmp_path)
    assert outcome.rendered is True
    assert outcome.finalized is False
    assert (tmp_path / ARTIFACTS_DIR / "working" / "report.html").exists()
    assert not (tmp_path / ARTIFACTS_DIR / "deliverables" / "final.html").exists()
    assert load_state(tmp_path).state != "final"


def test_renders_and_finalizes_when_criteria_pass(tmp_path: Path):
    init_artifacts(tmp_path)
    _set_required(tmp_path, status="passed", evidence="uv run pytest -q: passed")
    outcome = emit_report_on_stop(tmp_path)
    assert outcome.rendered is True
    assert outcome.finalized is True
    final_html = tmp_path / ARTIFACTS_DIR / "deliverables" / "final.html"
    assert final_html.exists()
    assert "Work complete" in final_html.read_text()
    assert load_state(tmp_path).state == "final"


def test_already_final_does_not_refinalize(tmp_path: Path):
    init_artifacts(tmp_path)
    _set_required(tmp_path, status="passed", evidence="ok")
    first = emit_report_on_stop(tmp_path)
    assert first.finalized is True
    stamp = load_state(tmp_path).updated_at

    second = emit_report_on_stop(tmp_path)
    assert second.rendered is True
    assert second.finalized is False
    assert load_state(tmp_path).updated_at == stamp  # no new state transition


def test_invalid_spec_returns_error_without_raising(tmp_path: Path):
    init_artifacts(tmp_path)
    (tmp_path / ARTIFACTS_DIR / "artifact_spec.yaml").write_text(
        "acceptance_criteria: [oops\n", encoding="utf-8"
    )
    outcome = emit_report_on_stop(tmp_path)  # must not raise
    assert outcome.error is not None
    assert outcome.rendered is False
