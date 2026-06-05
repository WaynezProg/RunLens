"""Stop-triggered HTML emission: refresh the working report and, when the
acceptance gate already passes, write the final deliverable.

Best-effort by contract — this runs from a lifecycle hook and must NEVER raise.
It reuses the same primitives and gate predicate as `runlens finalize`; it adds
no divergent gate logic.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from runlens.models import RunStatus
from runlens.renderer import (
    final_report_path,
    render_final_report,
    render_working_report,
)
from runlens.store import (
    SPEC_FILE,
    artifacts_root,
    build_updated_state,
    load_spec,
    load_state,
    write_state,
)

_FINAL_NOTE = "All required acceptance criteria passed."


@dataclass(frozen=True)
class ReportOutcome:
    rendered: bool = False
    finalized: bool = False
    working_report: str | None = None
    final_report: str | None = None
    skipped_no_artifacts: bool = False
    error: str | None = None

    def as_event_payload(self) -> dict:
        return {
            "rendered": self.rendered,
            "finalized": self.finalized,
            "working_report": self.working_report,
            "final_report": self.final_report,
            "skipped_no_artifacts": self.skipped_no_artifacts,
            "error": self.error,
        }


def _brief(exc: Exception) -> str:
    text = str(exc).strip().splitlines()
    return text[0] if text else exc.__class__.__name__


def _already_final(project_dir: Path) -> bool:
    if not final_report_path(project_dir).exists():
        return False
    try:
        return str(load_state(project_dir).state) == RunStatus.final.value
    except Exception:  # noqa: BLE001 - best-effort
        return False


def emit_report_on_stop(project_dir: Path) -> ReportOutcome:
    """Refresh the working report; finalize only when the gate already passes.

    Never raises. Skips entirely when the project has no artifact spec.
    """
    if not (artifacts_root(project_dir) / SPEC_FILE).exists():
        return ReportOutcome(skipped_no_artifacts=True)

    try:
        spec = load_spec(project_dir)
        working = render_working_report(project_dir)
    except Exception as exc:  # noqa: BLE001 - best-effort telemetry
        return ReportOutcome(error=_brief(exc))

    working_rel = working.relative_to(project_dir).as_posix()

    # Same predicate `finalize` uses. Only finalize when it will succeed —
    # finalize-on-fail sets state `failed` and deletes final.html.
    if not spec.required_criteria_passed() or _already_final(project_dir):
        return ReportOutcome(rendered=True, working_report=working_rel)

    try:
        final_report = final_report_path(project_dir)
        state = build_updated_state(
            project_dir,
            state=RunStatus.final,
            note=_FINAL_NOTE,
            last_report=final_report.relative_to(project_dir).as_posix(),
        )
        output = render_final_report(project_dir, state=state)
        write_state(project_dir, state)
    except Exception as exc:  # noqa: BLE001 - best-effort
        return ReportOutcome(rendered=True, working_report=working_rel, error=_brief(exc))

    return ReportOutcome(
        rendered=True,
        finalized=True,
        working_report=working_rel,
        final_report=output.relative_to(project_dir).as_posix(),
    )
