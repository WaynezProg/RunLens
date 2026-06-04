from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

import typer
import yaml
from pydantic import ValidationError

from runlens.models import RunStatus
from runlens.renderer import (
    checkpoint_report_path,
    final_report_path,
    render_checkpoint_report,
    render_final_report,
    render_working_report,
)
from runlens.store import (
    WORKING_REPORT,
    build_updated_state,
    default_spec,
    init_artifacts,
    load_spec,
    timestamp_for_filename,
    update_state,
    write_state,
)

app = typer.Typer(help="Manage RunLens .agent-artifacts.")
T = TypeVar("T")


def _run_initialized_command(action: Callable[[], T]) -> T:
    try:
        return action()
    except FileNotFoundError:
        typer.echo("Run runlens init first: .agent-artifacts not initialized.", err=True)
        raise typer.Exit(1) from None


@app.callback()
def _main() -> None:
    """Manage RunLens .agent-artifacts."""


@app.command("init")
def init_command() -> None:
    init_artifacts(Path.cwd())
    typer.echo("Initialized .agent-artifacts")


@app.command("update")
def update_command(
    state: RunStatus = typer.Option(..., "--state"),
    note: str = typer.Option(..., "--note"),
) -> None:
    _run_initialized_command(lambda: update_state(Path.cwd(), state=state, note=note))
    typer.echo(f"Updated state: {state.value}")


@app.command("render")
def render_command() -> None:
    output_path = _run_initialized_command(lambda: render_working_report(Path.cwd()))
    typer.echo(output_path)


@app.command("finalize")
def finalize_command(
    blocked_reason: str | None = typer.Option(None, "--blocked-reason"),
) -> None:
    def remove_final_report(base: Path) -> None:
        final_report_path(base).unlink(missing_ok=True)

    def fail_finalize(base: Path, note: str, banner: str, spec_is_valid: bool) -> None:
        state = build_updated_state(
            base,
            state=RunStatus.failed,
            note=note,
            last_report=WORKING_REPORT,
        )
        render_working_report(
            base,
            banner=banner,
            state=state,
            spec=default_spec() if not spec_is_valid else None,
        )
        remove_final_report(base)
        write_state(base, state)
        raise typer.Exit(1)

    def finalize_run() -> Path:
        base = Path.cwd()
        if blocked_reason:
            state = build_updated_state(
                base,
                state=RunStatus.blocked,
                note=blocked_reason,
                last_report=WORKING_REPORT,
            )
            render_working_report(
                base,
                banner=f"Blocked: {blocked_reason}",
                state=state,
            )
            remove_final_report(base)
            write_state(base, state)
            raise typer.Exit(1)

        try:
            spec = load_spec(base)
        except FileNotFoundError:
            raise
        except (TypeError, ValueError, ValidationError, yaml.YAMLError):
            fail_finalize(
                base,
                note="artifact_spec.yaml is invalid.",
                banner="Failed: artifact_spec.yaml is invalid.",
                spec_is_valid=False,
            )

        if not spec.required_criteria_passed():
            fail_finalize(
                base,
                note="Required acceptance criteria did not pass.",
                banner="Failed: required acceptance criteria did not pass.",
                spec_is_valid=True,
            )

        final_report = final_report_path(base)
        state = build_updated_state(
            base,
            state=RunStatus.final,
            note="All required acceptance criteria passed.",
            last_report=final_report.relative_to(base).as_posix(),
        )
        output_path = render_final_report(base, state=state)
        write_state(base, state)
        return output_path

    output_path = _run_initialized_command(finalize_run)
    typer.echo(output_path)


@app.command("checkpoint")
def checkpoint_command(
    reason: str = typer.Option(..., "--reason"),
) -> None:
    def create_checkpoint() -> Path:
        base = Path.cwd()
        timestamp = timestamp_for_filename()
        output_path = checkpoint_report_path(base, timestamp)
        state = build_updated_state(
            base,
            state=RunStatus.checkpoint,
            note=reason,
            last_report=output_path.relative_to(base).as_posix(),
        )
        render_checkpoint_report(base, reason=reason, timestamp=timestamp, state=state)
        write_state(base, state)
        return output_path

    output_path = _run_initialized_command(create_checkpoint)
    typer.echo(output_path)
