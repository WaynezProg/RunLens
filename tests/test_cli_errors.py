from pathlib import Path

import yaml
from typer.testing import CliRunner

from runlens.cli import app
from runlens.store import ARTIFACTS_DIR, load_state


def invoke_ok(runner: CliRunner, args: list[str]):
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    return result


def assert_invalid_artifact_data_error(output: str) -> None:
    assert output.startswith("Invalid RunLens artifact data:")
    assert len(output.splitlines()) <= 2
    assert "Traceback" not in output
    assert "ValidationError" not in output
    assert "JSONDecodeError" not in output


def test_render_invalid_run_state_json_exits_with_readable_error(
    isolated_cwd: Path,
):
    runner = CliRunner()
    invoke_ok(runner, ["init"])
    (isolated_cwd / ARTIFACTS_DIR / "run_state.json").write_text(
        "{",
        encoding="utf-8",
    )

    result = runner.invoke(app, ["render"])

    assert result.exit_code == 1
    assert_invalid_artifact_data_error(result.output)


def test_update_invalid_run_state_json_exits_with_readable_error(
    isolated_cwd: Path,
):
    runner = CliRunner()
    invoke_ok(runner, ["init"])
    (isolated_cwd / ARTIFACTS_DIR / "run_state.json").write_text(
        "{",
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        ["update", "--state", "working", "--note", "after corrupt state"],
    )

    assert result.exit_code == 1
    assert_invalid_artifact_data_error(result.output)


def test_checkpoint_invalid_artifact_spec_yaml_exits_with_readable_error(
    isolated_cwd: Path,
):
    runner = CliRunner()
    invoke_ok(runner, ["init"])
    previous_state = load_state(isolated_cwd)
    (isolated_cwd / ARTIFACTS_DIR / "artifact_spec.yaml").write_text(
        "task: [\n",
        encoding="utf-8",
    )

    result = runner.invoke(app, ["checkpoint", "--reason", "bad yaml"])

    assert result.exit_code == 1
    assert_invalid_artifact_data_error(result.output)
    assert load_state(isolated_cwd) == previous_state


def test_render_invalid_artifact_spec_schema_exits_with_readable_error(
    isolated_cwd: Path,
):
    runner = CliRunner()
    invoke_ok(runner, ["init"])
    spec_path = isolated_cwd / ARTIFACTS_DIR / "artifact_spec.yaml"
    spec = yaml.safe_load(spec_path.read_text())
    spec["acceptance_criteria"] = []
    spec_path.write_text(yaml.safe_dump(spec, sort_keys=False), encoding="utf-8")

    result = runner.invoke(app, ["render"])

    assert result.exit_code == 1
    assert_invalid_artifact_data_error(result.output)
