import threading
import time
from pathlib import Path

from runlens.autorender import (
    ArtifactWatchController,
    artifact_watch_paths,
    emit_working_report_on_change,
    watch_artifacts,
)
from runlens.models import AcceptanceCriterion, RunStatus
from runlens.store import ARTIFACTS_DIR, init_artifacts, load_spec, update_state, write_spec


def test_debounce_waits_quiet_period():
    clock = [0.0]

    def monotonic() -> float:
        return clock[0]

    ctrl = ArtifactWatchController(debounce_seconds=2.0, monotonic=monotonic)
    ctrl.observe_change(0.0)
    clock[0] = 1.5
    assert ctrl.should_render() is False
    clock[0] = 2.0
    assert ctrl.should_render() is False
    clock[0] = 2.01
    assert ctrl.should_render() is True


def test_debounce_coalesces_rapid_changes():
    clock = [0.0]

    def monotonic() -> float:
        return clock[0]

    ctrl = ArtifactWatchController(debounce_seconds=2.0, monotonic=monotonic)
    ctrl.observe_change(0.0)
    clock[0] = 0.5
    ctrl.observe_change()
    clock[0] = 1.0
    ctrl.observe_change()
    clock[0] = 2.5
    assert ctrl.should_render() is False  # only 1.5s since last change at 1.0
    clock[0] = 3.01
    assert ctrl.should_render() is True


def test_should_render_is_false_when_no_change():
    ctrl = ArtifactWatchController(debounce_seconds=2.0, monotonic=lambda: 100.0)
    assert ctrl.should_render() is False


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


def test_emit_skips_when_no_artifacts(tmp_path: Path):
    outcome = emit_working_report_on_change(tmp_path)
    assert outcome.skipped_no_artifacts is True
    assert outcome.rendered is False


def test_emit_renders_working_report(tmp_path: Path):
    init_artifacts(tmp_path)
    outcome = emit_working_report_on_change(tmp_path)
    assert outcome.rendered is True
    assert outcome.working_report == f"{ARTIFACTS_DIR}/working/report.html"
    assert (tmp_path / ARTIFACTS_DIR / "working" / "report.html").exists()


def test_emit_never_writes_final_html_even_when_gate_passes(tmp_path: Path):
    init_artifacts(tmp_path)
    _set_required(tmp_path, status="passed", evidence="uv run pytest -q: passed")
    outcome = emit_working_report_on_change(tmp_path)
    assert outcome.rendered is True
    assert not (tmp_path / ARTIFACTS_DIR / "deliverables" / "final.html").exists()


def test_emit_invalid_spec_returns_error_without_raising(tmp_path: Path):
    init_artifacts(tmp_path)
    (tmp_path / ARTIFACTS_DIR / "artifact_spec.yaml").write_text(
        "acceptance_criteria: [oops\n", encoding="utf-8"
    )
    outcome = emit_working_report_on_change(tmp_path)
    assert outcome.error is not None
    assert outcome.rendered is False


def test_artifact_watch_paths(tmp_path: Path):
    init_artifacts(tmp_path)
    spec_path, state_path = artifact_watch_paths(tmp_path)
    assert spec_path.name == "artifact_spec.yaml"
    assert state_path.name == "run_state.json"
    assert spec_path.exists()
    assert state_path.exists()


def test_watch_renders_after_debounced_state_change(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    init_artifacts(tmp_path)
    report = tmp_path / ARTIFACTS_DIR / "working" / "report.html"
    report.unlink(missing_ok=True)

    stop = threading.Event()

    def run_watch() -> None:
        watch_artifacts(
            tmp_path,
            debounce_seconds=0.1,
            poll_interval_seconds=0.05,
            stop_event=stop,
        )

    thread = threading.Thread(target=run_watch, daemon=True)
    thread.start()
    try:
        update_state(tmp_path, state=RunStatus.working, note="watch test")
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            if report.exists():
                break
            time.sleep(0.05)
        assert report.exists()
        assert "watch test" in report.read_text()
    finally:
        stop.set()
        thread.join(timeout=2.0)
