from __future__ import annotations

import typer

app = typer.Typer(help="Manage RunLens .agent-artifacts.")


@app.callback()
def _main() -> None:
    """Manage RunLens .agent-artifacts."""
