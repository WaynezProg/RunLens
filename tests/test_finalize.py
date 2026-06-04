from pathlib import Path

import yaml
from typer.testing import CliRunner

from runlens.cli import app
from runlens.store import ARTIFACTS_DIR, load_state


def write_criteria(isolated_cwd: Path, criteria: list[dict]) -> None:
    spec_path = isolated_cwd / ARTIFACTS_DIR / "artifact_spec.yaml"
    spec = yaml.safe_load(spec_path.read_text())
    spec["acceptance_criteria"] = criteria
    spec_path.write_text(yaml.safe_dump(spec, sort_keys=False))


def invoke_ok(runner: CliRunner, args: list[str]):
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    return result


def test_finalize_fails_nonzero_without_passed_required_criteria(
    isolated_cwd: Path,
):
    runner = CliRunner()
    invoke_ok(runner, ["init"])

    result = runner.invoke(app, ["finalize"])

    assert result.exit_code == 1
    assert load_state(isolated_cwd).state == "failed"
    assert not (
        isolated_cwd / ARTIFACTS_DIR / "deliverables" / "final.html"
    ).exists()
    assert (isolated_cwd / ARTIFACTS_DIR / "working" / "report.html").exists()


def test_finalize_failed_does_not_create_checkpoint(isolated_cwd: Path):
    runner = CliRunner()
    invoke_ok(runner, ["init"])

    result = runner.invoke(app, ["finalize"])

    assert result.exit_code == 1
    assert (
        list((isolated_cwd / ARTIFACTS_DIR / "checkpoints").glob("checkpoint-*.html"))
        == []
    )


def test_finalize_blocked_reason_sets_blocked_report_without_final(
    isolated_cwd: Path,
):
    runner = CliRunner()
    invoke_ok(runner, ["init"])

    result = runner.invoke(
        app,
        ["finalize", "--blocked-reason", "Missing API token"],
    )

    assert result.exit_code == 1
    assert load_state(isolated_cwd).state == "blocked"
    assert "Missing API token" in (
        isolated_cwd / ARTIFACTS_DIR / "working" / "report.html"
    ).read_text()
    assert not (
        isolated_cwd / ARTIFACTS_DIR / "deliverables" / "final.html"
    ).exists()


def test_finalize_blocked_does_not_create_final_html(isolated_cwd: Path):
    runner = CliRunner()
    invoke_ok(runner, ["init"])

    result = runner.invoke(app, ["finalize", "--blocked-reason", "waiting"])

    assert result.exit_code == 1
    assert not (
        isolated_cwd / ARTIFACTS_DIR / "deliverables" / "final.html"
    ).exists()


def test_finalize_blocked_removes_existing_final_html(isolated_cwd: Path):
    runner = CliRunner()
    invoke_ok(runner, ["init"])
    write_criteria(
        isolated_cwd,
        [
            {
                "id": "tests",
                "description": "Tests pass",
                "status": "passed",
                "evidence": "uv run pytest -q: passed",
                "required": True,
            }
        ],
    )
    invoke_ok(runner, ["finalize"])

    result = runner.invoke(app, ["finalize", "--blocked-reason", "waiting"])

    assert result.exit_code == 1
    assert not (
        isolated_cwd / ARTIFACTS_DIR / "deliverables" / "final.html"
    ).exists()


def test_finalize_requires_evidence_for_passed_required_criteria(
    isolated_cwd: Path,
):
    runner = CliRunner()
    invoke_ok(runner, ["init"])
    write_criteria(
        isolated_cwd,
        [
            {
                "id": "tests",
                "description": "Tests pass",
                "status": "passed",
                "evidence": "",
                "required": True,
            }
        ],
    )

    result = runner.invoke(app, ["finalize"])

    assert result.exit_code == 1
    assert load_state(isolated_cwd).state == "failed"
    assert not (
        isolated_cwd / ARTIFACTS_DIR / "deliverables" / "final.html"
    ).exists()


def test_finalize_failed_removes_existing_final_html(isolated_cwd: Path):
    runner = CliRunner()
    invoke_ok(runner, ["init"])
    write_criteria(
        isolated_cwd,
        [
            {
                "id": "tests",
                "description": "Tests pass",
                "status": "passed",
                "evidence": "uv run pytest -q: passed",
                "required": True,
            }
        ],
    )
    invoke_ok(runner, ["finalize"])
    write_criteria(
        isolated_cwd,
        [
            {
                "id": "tests",
                "description": "Tests pass",
                "status": "pending",
                "evidence": None,
                "required": True,
            }
        ],
    )

    result = runner.invoke(app, ["finalize"])

    assert result.exit_code == 1
    assert not (
        isolated_cwd / ARTIFACTS_DIR / "deliverables" / "final.html"
    ).exists()


def test_finalize_uses_artifact_spec_not_run_state_note(isolated_cwd: Path):
    runner = CliRunner()
    invoke_ok(runner, ["init"])
    invoke_ok(
        runner,
        [
            "update",
            "--state",
            "working",
            "--note",
            "All required acceptance criteria passed with evidence.",
        ],
    )

    result = runner.invoke(app, ["finalize"])

    assert result.exit_code == 1
    assert load_state(isolated_cwd).state == "failed"
    assert not (
        isolated_cwd / ARTIFACTS_DIR / "deliverables" / "final.html"
    ).exists()


def test_finalize_succeeds_only_when_required_criteria_pass_with_evidence(
    isolated_cwd: Path,
):
    runner = CliRunner()
    invoke_ok(runner, ["init"])
    write_criteria(
        isolated_cwd,
        [
            {
                "id": "tests",
                "description": "Tests pass",
                "status": "passed",
                "evidence": "uv run pytest -q: passed",
                "required": True,
            },
            {
                "id": "nice-to-have",
                "description": "Optional polish",
                "status": "pending",
                "evidence": None,
                "required": False,
            },
        ],
    )

    result = runner.invoke(app, ["finalize"])

    assert result.exit_code == 0
    assert load_state(isolated_cwd).state == "final"
    final_html = isolated_cwd / ARTIFACTS_DIR / "deliverables" / "final.html"
    assert final_html.exists()
    assert "Tests pass" in final_html.read_text()


def test_finalize_before_init_exits_with_user_facing_error(isolated_cwd: Path):
    runner = CliRunner()

    result = runner.invoke(app, ["finalize"])

    assert result.exit_code != 0
    assert "Run runlens init first" in result.output
    assert "Traceback" not in result.output
    assert "FileNotFoundError" not in result.output
