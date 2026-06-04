import json
from datetime import UTC, datetime
from pathlib import Path

import yaml
from typer.testing import CliRunner

import runlens.store as store
from runlens.cli import app
from runlens.store import (
    ARTIFACTS_DIR,
    init_artifacts,
    load_spec,
    load_state,
    update_state,
    write_spec,
)


def invoke_ok(runner: CliRunner, args: list[str]):
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    return result


def test_init_creates_protocol_tree_and_placeholder_criterion(isolated_cwd: Path):
    init_artifacts(isolated_cwd)

    root = isolated_cwd / ARTIFACTS_DIR
    assert (root / "artifact_spec.yaml").is_file()
    assert (root / "run_state.json").is_file()
    assert (root / "RUN_STATE.md").is_file()
    assert (root / "working" / "data").is_dir()
    assert (root / "working" / "charts").is_dir()
    assert (root / "checkpoints").is_dir()
    assert (root / "deliverables").is_dir()

    spec = yaml.safe_load((root / "artifact_spec.yaml").read_text())
    assert spec["acceptance_criteria"] == [
        {
            "id": "define-criteria",
            "description": "Replace this placeholder with task-specific acceptance criteria.",
            "status": "pending",
            "evidence": None,
            "required": True,
        }
    ]


def test_update_changes_state_files_but_not_acceptance_criteria(isolated_cwd: Path):
    init_artifacts(isolated_cwd)
    before_spec = (isolated_cwd / ARTIFACTS_DIR / "artifact_spec.yaml").read_text()

    state = update_state(isolated_cwd, state="working", note="implemented parser")

    assert state.state == "working"
    assert state.note == "implemented parser"
    assert load_state(isolated_cwd).note == "implemented parser"
    assert "implemented parser" in (isolated_cwd / ARTIFACTS_DIR / "RUN_STATE.md").read_text()
    assert (isolated_cwd / ARTIFACTS_DIR / "artifact_spec.yaml").read_text() == before_spec
    assert load_spec(isolated_cwd).acceptance_criteria[0].id == "define-criteria"


def test_update_changes_updated_at_when_run_immediately_after_init(
    isolated_cwd: Path, monkeypatch
):
    timestamps = iter(
        [
            datetime(2026, 6, 4, 12, 0, 0, 100, tzinfo=UTC),
            datetime(2026, 6, 4, 12, 0, 0, 200, tzinfo=UTC),
        ]
    )

    class SameSecondDatetime:
        @classmethod
        def now(cls, tz):
            return next(timestamps)

    monkeypatch.setattr(store, "datetime", SameSecondDatetime)

    init_artifacts(isolated_cwd)
    previous = load_state(isolated_cwd)
    updated = update_state(isolated_cwd, state="working", note="implemented parser")

    assert updated.updated_at != previous.updated_at


def test_init_preserves_existing_contract_and_state(isolated_cwd: Path):
    init_artifacts(isolated_cwd)
    spec = load_spec(isolated_cwd)
    spec.acceptance_criteria[0].status = "passed"
    spec.acceptance_criteria[0].evidence = ".agent-artifacts/working/report.html"
    write_spec(isolated_cwd, spec)
    update_state(isolated_cwd, state="working", note="kept existing evidence")
    markdown_path = isolated_cwd / ARTIFACTS_DIR / "RUN_STATE.md"
    before_markdown = markdown_path.read_text()

    init_artifacts(isolated_cwd)

    preserved_spec = load_spec(isolated_cwd)
    preserved_state = load_state(isolated_cwd)
    assert preserved_spec.acceptance_criteria[0].status == "passed"
    assert (
        preserved_spec.acceptance_criteria[0].evidence
        == ".agent-artifacts/working/report.html"
    )
    assert preserved_state.note == "kept existing evidence"
    assert markdown_path.read_text() == before_markdown


def test_init_regenerates_missing_state_markdown_from_existing_state(isolated_cwd: Path):
    init_artifacts(isolated_cwd)
    update_state(isolated_cwd, state="working", note="state survives missing markdown")
    markdown_path = isolated_cwd / ARTIFACTS_DIR / "RUN_STATE.md"
    markdown_path.unlink()

    init_artifacts(isolated_cwd)

    assert load_state(isolated_cwd).note == "state survives missing markdown"
    assert markdown_path.is_file()
    assert "state survives missing markdown" in markdown_path.read_text()


def test_run_state_json_does_not_copy_acceptance_criteria(isolated_cwd: Path):
    init_artifacts(isolated_cwd)

    raw_state = json.loads((isolated_cwd / ARTIFACTS_DIR / "run_state.json").read_text())

    assert "acceptance_criteria" not in raw_state


def test_cli_init_creates_placeholder_contract(isolated_cwd: Path):
    runner = CliRunner()

    result = runner.invoke(app, ["init"])

    assert result.exit_code == 0
    assert (isolated_cwd / ARTIFACTS_DIR / "artifact_spec.yaml").exists()
    assert load_spec(isolated_cwd).acceptance_criteria[0].status == "pending"


def test_cli_update_writes_run_state_only(isolated_cwd: Path):
    runner = CliRunner()
    invoke_ok(runner, ["init"])
    before_spec = (isolated_cwd / ARTIFACTS_DIR / "artifact_spec.yaml").read_text()

    result = runner.invoke(
        app, ["update", "--state", "working", "--note", "implemented parser"]
    )

    assert result.exit_code == 0
    assert load_state(isolated_cwd).note == "implemented parser"
    assert (isolated_cwd / ARTIFACTS_DIR / "artifact_spec.yaml").read_text() == before_spec


def test_cli_update_before_init_exits_with_user_facing_error(isolated_cwd: Path):
    runner = CliRunner()

    result = runner.invoke(
        app, ["update", "--state", "working", "--note", "implemented parser"]
    )

    assert result.exit_code != 0
    assert "Run runlens init first" in result.output
    assert "Traceback" not in result.output
    assert "FileNotFoundError" not in result.output
