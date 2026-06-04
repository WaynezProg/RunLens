from __future__ import annotations

from pathlib import Path

import typer

from runlens.models import RunStatus
from runlens.renderer import render_working_report
from runlens.store import init_artifacts, update_state

app = typer.Typer(help="Manage RunLens .agent-artifacts.")


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
    update_state(Path.cwd(), state=state, note=note)
    typer.echo(f"Updated state: {state.value}")


@app.command("render")
def render_command() -> None:
    output_path = render_working_report(Path.cwd())
    typer.echo(output_path)
