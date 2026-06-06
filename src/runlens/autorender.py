from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from threading import Event

from runlens.renderer import render_working_report
from runlens.store import SPEC_FILE, STATE_FILE, artifacts_root


class ArtifactWatchController:
    """Debounce artifact-file changes before triggering a render."""

    def __init__(
        self,
        debounce_seconds: float,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._debounce_seconds = debounce_seconds
        self._monotonic = monotonic
        self._change_at: float | None = None

    def observe_change(self, at: float | None = None) -> None:
        self._change_at = at if at is not None else self._monotonic()

    def should_render(self, at: float | None = None) -> bool:
        now = at if at is not None else self._monotonic()
        if self._change_at is None:
            return False
        if now - self._change_at <= self._debounce_seconds:
            return False
        self._change_at = None
        return True


@dataclass(frozen=True)
class AutorenderOutcome:
    rendered: bool = False
    working_report: str | None = None
    skipped_no_artifacts: bool = False
    error: str | None = None


def _brief(exc: Exception) -> str:
    text = str(exc).strip().splitlines()
    return text[0] if text else exc.__class__.__name__


def emit_working_report_on_change(project_dir: Path) -> AutorenderOutcome:
    """Render working/report.html only. Never finalize. Never raises."""
    if not (artifacts_root(project_dir) / SPEC_FILE).exists():
        return AutorenderOutcome(skipped_no_artifacts=True)

    try:
        working = render_working_report(project_dir)
    except Exception as exc:  # noqa: BLE001 - best-effort
        return AutorenderOutcome(error=_brief(exc))

    return AutorenderOutcome(
        rendered=True,
        working_report=working.relative_to(project_dir).as_posix(),
    )


def artifact_watch_paths(project_dir: Path) -> tuple[Path, Path]:
    root = artifacts_root(project_dir)
    return root / SPEC_FILE, root / STATE_FILE


def _mtime_snapshot(paths: tuple[Path, ...]) -> tuple[int, ...]:
    return tuple(path.stat().st_mtime_ns if path.exists() else 0 for path in paths)


def watch_artifacts(
    project_dir: Path,
    *,
    debounce_seconds: float = 2.0,
    poll_interval_seconds: float = 0.25,
    stop_event: Event | None = None,
) -> None:
    """Poll artifact spec/state mtimes; debounce-render working report. Blocks until stop."""
    paths = artifact_watch_paths(project_dir)
    if not paths[0].exists():
        msg = f"Missing {SPEC_FILE}; run `runlens init` first."
        raise FileNotFoundError(msg)

    controller = ArtifactWatchController(debounce_seconds=debounce_seconds)
    last_seen = _mtime_snapshot(paths)

    while stop_event is None or not stop_event.is_set():
        time.sleep(poll_interval_seconds)
        current = _mtime_snapshot(paths)
        if current != last_seen:
            last_seen = current
            controller.observe_change()
        if controller.should_render():
            emit_working_report_on_change(project_dir)
