from __future__ import annotations

import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

import typer
import yaml
from pydantic import ValidationError

from runlens.criteria import (
    CriteriaCommandError,
    add_criterion,
    reset_criterion,
    set_criterion_status,
)
from runlens.hook import normalize_and_append
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
    write_spec,
    write_state,
)

app = typer.Typer(help="Manage RunLens .agent-artifacts.")
criteria_app = typer.Typer(help="Maintain artifact_spec.yaml acceptance criteria.")
app.add_typer(criteria_app, name="criteria")
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


def _run_criteria_command(action: Callable[[], T]) -> T:
    try:
        return _run_initialized_command(action)
    except CriteriaCommandError as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(1) from None


def _load_update_write_spec(
    mutator: Callable[[ArtifactSpec], ArtifactSpec],
) -> ArtifactSpec:
    base = Path.cwd()
    spec = load_spec(base)
    next_spec = mutator(spec)
    write_spec(base, next_spec)
    return next_spec


@app.callback()
def _main() -> None:
    """Manage RunLens .agent-artifacts."""


@criteria_app.command("list")
def criteria_list_command() -> None:
    def list_criteria() -> list[str]:
        spec = load_spec(Path.cwd())
        return [
            (
                f"{criterion.id}\t{criterion.status}\t"
                f"required={str(criterion.required).lower()}\t"
                f"evidence={criterion.evidence or ''}\t"
                f"{criterion.description}"
            )
            for criterion in spec.acceptance_criteria
        ]

    for line in _run_initialized_command(list_criteria):
        typer.echo(line)


@criteria_app.command("add")
def criteria_add_command(
    criterion_id: str = typer.Option(..., "--id"),
    description: str = typer.Option(..., "--description"),
    required: bool = typer.Option(False, "--required"),
) -> None:
    _run_criteria_command(
        lambda: _load_update_write_spec(
            lambda spec: add_criterion(
                spec,
                criterion_id=criterion_id,
                description=description,
                required=required,
            )
        )
    )
    typer.echo(f"Added criterion: {criterion_id}")


@criteria_app.command("pass")
def criteria_pass_command(
    criterion_id: str = typer.Option(..., "--id"),
    evidence: str = typer.Option(..., "--evidence"),
) -> None:
    _run_criteria_command(
        lambda: _load_update_write_spec(
            lambda spec: set_criterion_status(
                spec,
                criterion_id=criterion_id,
                status="passed",
                evidence=evidence,
            )
        )
    )
    typer.echo(f"Passed criterion: {criterion_id}")


@criteria_app.command("fail")
def criteria_fail_command(
    criterion_id: str = typer.Option(..., "--id"),
    evidence: str = typer.Option(..., "--evidence"),
) -> None:
    _run_criteria_command(
        lambda: _load_update_write_spec(
            lambda spec: set_criterion_status(
                spec,
                criterion_id=criterion_id,
                status="failed",
                evidence=evidence,
            )
        )
    )
    typer.echo(f"Failed criterion: {criterion_id}")


@criteria_app.command("reset")
def criteria_reset_command(
    criterion_id: str = typer.Option(..., "--id"),
) -> None:
    _run_criteria_command(
        lambda: _load_update_write_spec(
            lambda spec: reset_criterion(spec, criterion_id=criterion_id)
        )
    )
    typer.echo(f"Reset criterion: {criterion_id}")


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


@app.command("hook")
def hook_command(
    event: str = typer.Option(..., "--event", help="Event name (e.g. SessionStart)"),
    agent: str = typer.Option(..., "--agent", help="Agent runtime (claude-code|codex|opencode|cursor)"),
) -> None:
    """Normalize a lifecycle event and append to hooks.jsonl."""
    stdin_data = sys.stdin.read()
    normalized = normalize_and_append(event=event, agent=agent, stdin_data=stdin_data)
    typer.echo(json.dumps(normalized, ensure_ascii=True))
