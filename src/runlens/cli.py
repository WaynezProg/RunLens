from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

import typer
import yaml
from pydantic import ValidationError

from runlens.models import ArtifactSpec, RunStatus
from runlens.renderer import (
    checkpoint_report_path,
    final_report_path,
    render_checkpoint_report,
    render_final_report,
    render_working_report,
)
from runlens.store import (
    STATE_FILE,
    WORKING_REPORT,
    artifacts_root,
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
ARTIFACT_DATA_ERRORS = (
    json.JSONDecodeError,
    yaml.YAMLError,
    ValidationError,
    TypeError,
    ValueError,
)


def _brief_artifact_error(error: Exception) -> str:
    if isinstance(error, ValidationError):
        first_error = error.errors()[0] if error.errors() else {}
        location = ".".join(str(part) for part in first_error.get("loc", ()))
        message = str(first_error.get("msg", "schema validation failed"))
        return f"{location}: {message}" if location else message

    message = str(error).strip().splitlines()
    return message[0] if message else error.__class__.__name__


def _run_initialized_command(action: Callable[[], T]) -> T:
    try:
        return action()
    except FileNotFoundError:
        typer.echo("Run runlens init first: .agent-artifacts not initialized.", err=True)
        raise typer.Exit(1) from None
    except ARTIFACT_DATA_ERRORS as error:
        typer.echo(
            f"Invalid RunLens artifact data: {_brief_artifact_error(error)}",
            err=True,
        )
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

    def load_report_spec(base: Path) -> ArtifactSpec:
        try:
            return load_spec(base)
        except (
            FileNotFoundError,
            TypeError,
            ValueError,
            ValidationError,
            yaml.YAMLError,
        ):
            return default_spec()

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
        typer.echo(banner, err=True)
        raise typer.Exit(1)

    def block_finalize(base: Path, note: str, banner: str) -> None:
        state = build_updated_state(
            base,
            state=RunStatus.blocked,
            note=note,
            last_report=WORKING_REPORT,
        )
        render_working_report(
            base,
            banner=banner,
            state=state,
            spec=load_report_spec(base),
        )
        remove_final_report(base)
        write_state(base, state)
        typer.echo(banner, err=True)
        raise typer.Exit(1)

    def finalize_run() -> Path:
        base = Path.cwd()
        if blocked_reason is not None:
            reason = blocked_reason.strip()
            if not reason:
                typer.echo("Blocked reason cannot be empty.", err=True)
                raise typer.Exit(1)
            block_finalize(
                base,
                note=reason,
                banner=f"Blocked: {reason}",
            )

        try:
            spec = load_spec(base)
        except FileNotFoundError:
            if (artifacts_root(base) / STATE_FILE).exists():
                fail_finalize(
                    base,
                    note="artifact_spec.yaml is missing.",
                    banner="Failed: artifact_spec.yaml is missing.",
                    spec_is_valid=False,
                )
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
