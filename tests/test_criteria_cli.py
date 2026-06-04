from pathlib import Path

from typer.testing import CliRunner

from runlens.cli import app
from runlens.store import ARTIFACTS_DIR, load_spec, load_state


def invoke_ok(runner: CliRunner, args: list[str]):
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    return result


def artifact_spec_path(cwd: Path) -> Path:
    return cwd / ARTIFACTS_DIR / "artifact_spec.yaml"


def snapshot_state_files(cwd: Path) -> tuple[str, str]:
    root = cwd / ARTIFACTS_DIR
    return (
        (root / "run_state.json").read_text(encoding="utf-8"),
        (root / "RUN_STATE.md").read_text(encoding="utf-8"),
    )


def test_criteria_list_prints_stable_lines_without_mutating_files(
    isolated_cwd: Path,
):
    runner = CliRunner()
    invoke_ok(runner, ["init"])
    before_spec = artifact_spec_path(isolated_cwd).read_text(encoding="utf-8")
    before_state = snapshot_state_files(isolated_cwd)

    result = runner.invoke(app, ["criteria", "list"])

    assert result.exit_code == 0
    assert (
        "define-criteria\tpending\trequired=true\tevidence=\t"
        "Replace this placeholder with task-specific acceptance criteria."
    ) in result.output
    assert artifact_spec_path(isolated_cwd).read_text(encoding="utf-8") == before_spec
    assert snapshot_state_files(isolated_cwd) == before_state


def test_criteria_add_creates_pending_criteria_from_required_flag(
    isolated_cwd: Path,
):
    runner = CliRunner()
    invoke_ok(runner, ["init"])
    before_state = snapshot_state_files(isolated_cwd)

    invoke_ok(
        runner,
        [
            "criteria",
            "add",
            "--id",
            "tests",
            "--description",
            "Tests pass",
            "--required",
        ],
    )
    invoke_ok(
        runner,
        [
            "criteria",
            "add",
            "--id",
            "optional-polish",
            "--description",
            "Optional polish",
        ],
    )

    spec = load_spec(isolated_cwd)
    tests = next(
        criterion for criterion in spec.acceptance_criteria if criterion.id == "tests"
    )
    optional = next(
        criterion
        for criterion in spec.acceptance_criteria
        if criterion.id == "optional-polish"
    )
    assert tests.description == "Tests pass"
    assert tests.status == "pending"
    assert tests.evidence is None
    assert tests.required is True
    assert optional.required is False
    assert snapshot_state_files(isolated_cwd) == before_state


def test_criteria_add_duplicate_id_exits_nonzero_without_mutating_spec(
    isolated_cwd: Path,
):
    runner = CliRunner()
    invoke_ok(runner, ["init"])
    before_spec = artifact_spec_path(isolated_cwd).read_text(encoding="utf-8")
    before_state = snapshot_state_files(isolated_cwd)

    result = runner.invoke(
        app,
        [
            "criteria",
            "add",
            "--id",
            "define-criteria",
            "--description",
            "Replacement",
        ],
    )

    assert result.exit_code == 1
    assert "Criterion already exists: define-criteria" in result.output
    assert artifact_spec_path(isolated_cwd).read_text(encoding="utf-8") == before_spec
    assert snapshot_state_files(isolated_cwd) == before_state


def test_criteria_pass_rejects_empty_evidence_without_mutating_spec(
    isolated_cwd: Path,
):
    runner = CliRunner()
    invoke_ok(runner, ["init"])
    before_spec = artifact_spec_path(isolated_cwd).read_text(encoding="utf-8")
    before_state = snapshot_state_files(isolated_cwd)

    result = runner.invoke(
        app,
        ["criteria", "pass", "--id", "define-criteria", "--evidence", "   "],
    )

    assert result.exit_code == 1
    assert "Evidence cannot be empty." in result.output
    assert artifact_spec_path(isolated_cwd).read_text(encoding="utf-8") == before_spec
    assert snapshot_state_files(isolated_cwd) == before_state


def test_criteria_pass_sets_passed_status_and_evidence_without_state_mutation(
    isolated_cwd: Path,
):
    runner = CliRunner()
    invoke_ok(runner, ["init"])
    before_state = snapshot_state_files(isolated_cwd)

    invoke_ok(
        runner,
        [
            "criteria",
            "pass",
            "--id",
            "define-criteria",
            "--evidence",
            "uv run pytest -q: 60 passed",
        ],
    )

    criterion = load_spec(isolated_cwd).acceptance_criteria[0]
    assert criterion.status == "passed"
    assert criterion.evidence == "uv run pytest -q: 60 passed"
    assert snapshot_state_files(isolated_cwd) == before_state


def test_criteria_fail_sets_failed_status_and_evidence_without_state_mutation(
    isolated_cwd: Path,
):
    runner = CliRunner()
    invoke_ok(runner, ["init"])
    before_state = snapshot_state_files(isolated_cwd)

    invoke_ok(
        runner,
        [
            "criteria",
            "fail",
            "--id",
            "define-criteria",
            "--evidence",
            "pytest failed: assertion error",
        ],
    )

    criterion = load_spec(isolated_cwd).acceptance_criteria[0]
    assert criterion.status == "failed"
    assert criterion.evidence == "pytest failed: assertion error"
    assert snapshot_state_files(isolated_cwd) == before_state


def test_criteria_reset_returns_pending_and_clears_evidence_without_state_mutation(
    isolated_cwd: Path,
):
    runner = CliRunner()
    invoke_ok(runner, ["init"])
    invoke_ok(
        runner,
        [
            "criteria",
            "pass",
            "--id",
            "define-criteria",
            "--evidence",
            "manual verification",
        ],
    )
    before_state = snapshot_state_files(isolated_cwd)

    invoke_ok(runner, ["criteria", "reset", "--id", "define-criteria"])

    criterion = load_spec(isolated_cwd).acceptance_criteria[0]
    assert criterion.status == "pending"
    assert criterion.evidence is None
    assert snapshot_state_files(isolated_cwd) == before_state


def test_criteria_mutations_reject_missing_id_without_mutating_spec(
    isolated_cwd: Path,
):
    runner = CliRunner()
    invoke_ok(runner, ["init"])

    for args in (
        ["criteria", "pass", "--id", "tests", "--evidence", "passed"],
        ["criteria", "fail", "--id", "tests", "--evidence", "failed"],
        ["criteria", "reset", "--id", "tests"],
    ):
        before_spec = artifact_spec_path(isolated_cwd).read_text(encoding="utf-8")
        before_state = snapshot_state_files(isolated_cwd)

        result = runner.invoke(app, args)

        assert result.exit_code == 1
        assert "Criterion not found: tests" in result.output
        assert (
            artifact_spec_path(isolated_cwd).read_text(encoding="utf-8")
            == before_spec
        )
        assert snapshot_state_files(isolated_cwd) == before_state


def test_finalize_still_uses_required_criteria_gate_after_criteria_commands(
    isolated_cwd: Path,
):
    runner = CliRunner()
    invoke_ok(runner, ["init"])
    invoke_ok(
        runner,
        [
            "criteria",
            "add",
            "--id",
            "tests",
            "--description",
            "Tests pass",
            "--required",
        ],
    )
    invoke_ok(
        runner,
        [
            "criteria",
            "pass",
            "--id",
            "define-criteria",
            "--evidence",
            "Criteria UX defined",
        ],
    )
    invoke_ok(
        runner,
        [
            "criteria",
            "pass",
            "--id",
            "tests",
            "--evidence",
            "uv run pytest -q: 60 passed",
        ],
    )

    result = runner.invoke(app, ["finalize"])

    assert result.exit_code == 0
    assert load_state(isolated_cwd).state == "final"
    assert (
        isolated_cwd / ARTIFACTS_DIR / "deliverables" / "final.html"
    ).exists()
