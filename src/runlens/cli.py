from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

import typer

from runlens.models import RunStatus
from runlens.renderer import (
    checkpoint_report_path,
    render_checkpoint_report,
    render_working_report,
)
from runlens.store import (
    build_updated_state,
    init_artifacts,
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
