# RunLens Criteria UX Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `runlens criteria` commands so agents can maintain acceptance criteria through the CLI instead of hand-editing `artifact_spec.yaml`.

**Architecture:** Add a focused `src/runlens/criteria.py` helper module for pure `ArtifactSpec` data operations. Add a Typer `criteria` subgroup in `src/runlens/cli.py` that loads/writes `artifact_spec.yaml`, maps expected helper errors to readable non-zero exits, and never touches run state, renderer output, checkpoint output, or finalize internals.

**Tech Stack:** Python 3.13, uv, Typer, Pydantic, PyYAML, pytest.

---

## File Structure

- Create: `src/runlens/criteria.py` - pure acceptance-criteria data helpers and typed expected errors.
- Create: `tests/test_criteria_helpers.py` - unit tests for helper behavior without filesystem or Typer.
- Create: `tests/test_criteria_cli.py` - CLI tests for `runlens criteria` behavior, file mutation boundaries, and finalize compatibility.
- Modify: `src/runlens/cli.py` - register `criteria` Typer subgroup and wire commands to helper functions.
- Do not modify: `src/runlens/renderer.py`, `src/runlens/templates/report.html.j2`, adapter docs, chart behavior, or finalize gate semantics.
- Do not modify for this feature: `pyproject.toml` or `src/runlens/__init__.py`; the v0.2.0 label belongs to the feature spec, not a release/version bump.

---

### Task 1: Add Pure Criteria Helpers

**Files:**
- Create: `tests/test_criteria_helpers.py`
- Create: `src/runlens/criteria.py`

- [ ] **Step 1: Write failing helper tests**

Create `tests/test_criteria_helpers.py`:

```python
import pytest

from runlens.criteria import (
    CriterionAlreadyExistsError,
    CriterionNotFoundError,
    EmptyEvidenceError,
    add_criterion,
    reset_criterion,
    set_criterion_status,
)
from runlens.models import AcceptanceCriterion, ArtifactSpec, TaskInfo


def make_spec() -> ArtifactSpec:
    return ArtifactSpec(
        task=TaskInfo(title="Task", description="Description"),
        acceptance_criteria=[
            AcceptanceCriterion(
                id="define-criteria",
                description="Define task-specific criteria.",
                status="pending",
                evidence=None,
                required=True,
            )
        ],
        artifacts=[],
        charts=[],
    )


def test_add_criterion_appends_pending_without_mutating_original():
    spec = make_spec()

    next_spec = add_criterion(
        spec,
        criterion_id="tests",
        description="Tests pass",
        required=True,
    )

    assert [criterion.id for criterion in spec.acceptance_criteria] == [
        "define-criteria"
    ]
    added = next_spec.acceptance_criteria[1]
    assert added.id == "tests"
    assert added.description == "Tests pass"
    assert added.status == "pending"
    assert added.evidence is None
    assert added.required is True


def test_add_criterion_uses_required_flag_false():
    spec = make_spec()

    next_spec = add_criterion(
        spec,
        criterion_id="optional-polish",
        description="Optional polish",
        required=False,
    )

    assert next_spec.acceptance_criteria[1].required is False


def test_add_criterion_rejects_duplicate_id_without_mutating_original():
    spec = make_spec()

    with pytest.raises(
        CriterionAlreadyExistsError,
        match="Criterion already exists: define-criteria",
    ):
        add_criterion(
            spec,
            criterion_id="define-criteria",
            description="Replacement",
            required=False,
        )

    criterion = spec.acceptance_criteria[0]
    assert criterion.description == "Define task-specific criteria."
    assert criterion.status == "pending"
    assert criterion.evidence is None
    assert criterion.required is True


def test_set_criterion_status_passed_requires_non_empty_evidence():
    spec = make_spec()

    with pytest.raises(EmptyEvidenceError, match="Evidence cannot be empty."):
        set_criterion_status(
            spec,
            criterion_id="define-criteria",
            status="passed",
            evidence="   ",
        )

    assert spec.acceptance_criteria[0].status == "pending"
    assert spec.acceptance_criteria[0].evidence is None


def test_set_criterion_status_passed_records_trimmed_evidence():
    spec = make_spec()

    next_spec = set_criterion_status(
        spec,
        criterion_id="define-criteria",
        status="passed",
        evidence="  uv run pytest -q: 60 passed  ",
    )

    criterion = next_spec.acceptance_criteria[0]
    assert criterion.status == "passed"
    assert criterion.evidence == "uv run pytest -q: 60 passed"


def test_set_criterion_status_failed_records_evidence():
    spec = make_spec()

    next_spec = set_criterion_status(
        spec,
        criterion_id="define-criteria",
        status="failed",
        evidence="pytest failed: assertion error",
    )

    criterion = next_spec.acceptance_criteria[0]
    assert criterion.status == "failed"
    assert criterion.evidence == "pytest failed: assertion error"


def test_reset_criterion_returns_pending_and_clears_evidence():
    spec = set_criterion_status(
        make_spec(),
        criterion_id="define-criteria",
        status="passed",
        evidence="manual verification",
    )

    next_spec = reset_criterion(spec, criterion_id="define-criteria")

    criterion = next_spec.acceptance_criteria[0]
    assert criterion.status == "pending"
    assert criterion.evidence is None
    assert criterion.id == "define-criteria"
    assert criterion.description == "Define task-specific criteria."
    assert criterion.required is True


def test_set_criterion_status_rejects_missing_id():
    spec = make_spec()

    with pytest.raises(CriterionNotFoundError, match="Criterion not found: tests"):
        set_criterion_status(
            spec,
            criterion_id="tests",
            status="failed",
            evidence="not run",
        )


def test_reset_criterion_rejects_missing_id():
    spec = make_spec()

    with pytest.raises(CriterionNotFoundError, match="Criterion not found: tests"):
        reset_criterion(spec, criterion_id="tests")
```

- [ ] **Step 2: Run helper tests and verify RED**

Run:

```bash
uv run pytest tests/test_criteria_helpers.py -q
```

Expected: command exits non-zero with `ModuleNotFoundError: No module named 'runlens.criteria'`.

- [ ] **Step 3: Implement pure criteria helper module**

Create `src/runlens/criteria.py`:

```python
from __future__ import annotations

from runlens.models import AcceptanceCriterion, ArtifactSpec, CriterionStatus


class CriteriaCommandError(Exception):
    """Expected criteria command error that should be shown without traceback."""


class CriterionAlreadyExistsError(CriteriaCommandError):
    def __init__(self, criterion_id: str) -> None:
        super().__init__(f"Criterion already exists: {criterion_id}")


class CriterionNotFoundError(CriteriaCommandError):
    def __init__(self, criterion_id: str) -> None:
        super().__init__(f"Criterion not found: {criterion_id}")


class EmptyEvidenceError(CriteriaCommandError):
    def __init__(self) -> None:
        super().__init__("Evidence cannot be empty.")


def _criterion_index(spec: ArtifactSpec, criterion_id: str) -> int:
    for index, criterion in enumerate(spec.acceptance_criteria):
        if criterion.id == criterion_id:
            return index
    raise CriterionNotFoundError(criterion_id)


def _replace_criterion(
    spec: ArtifactSpec,
    *,
    index: int,
    criterion: AcceptanceCriterion,
) -> ArtifactSpec:
    criteria = list(spec.acceptance_criteria)
    criteria[index] = criterion
    return spec.model_copy(update={"acceptance_criteria": criteria})


def add_criterion(
    spec: ArtifactSpec,
    *,
    criterion_id: str,
    description: str,
    required: bool,
) -> ArtifactSpec:
    if any(criterion.id == criterion_id for criterion in spec.acceptance_criteria):
        raise CriterionAlreadyExistsError(criterion_id)

    criterion = AcceptanceCriterion(
        id=criterion_id,
        description=description,
        status="pending",
        evidence=None,
        required=required,
    )
    return spec.model_copy(
        update={"acceptance_criteria": [*spec.acceptance_criteria, criterion]}
    )


def set_criterion_status(
    spec: ArtifactSpec,
    *,
    criterion_id: str,
    status: CriterionStatus,
    evidence: str | None,
) -> ArtifactSpec:
    index = _criterion_index(spec, criterion_id)
    normalized_evidence = evidence.strip() if isinstance(evidence, str) else evidence
    if status == "passed" and not normalized_evidence:
        raise EmptyEvidenceError()

    criterion = spec.acceptance_criteria[index].model_copy(
        update={"status": status, "evidence": normalized_evidence}
    )
    return _replace_criterion(spec, index=index, criterion=criterion)


def reset_criterion(spec: ArtifactSpec, *, criterion_id: str) -> ArtifactSpec:
    index = _criterion_index(spec, criterion_id)
    criterion = spec.acceptance_criteria[index].model_copy(
        update={"status": "pending", "evidence": None}
    )
    return _replace_criterion(spec, index=index, criterion=criterion)
```

- [ ] **Step 4: Run helper tests and verify GREEN**

Run:

```bash
uv run pytest tests/test_criteria_helpers.py -q
```

Expected:

```text
9 passed
```

- [ ] **Step 5: Commit helper layer**

Run:

```bash
git add src/runlens/criteria.py tests/test_criteria_helpers.py
git commit -m "feat: add criteria spec helpers"
```

---

### Task 2: Add Criteria CLI Tests

**Files:**
- Create: `tests/test_criteria_cli.py`

- [ ] **Step 1: Write failing CLI tests**

Create `tests/test_criteria_cli.py`:

```python
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
```

- [ ] **Step 2: Run CLI tests and verify RED**

Run:

```bash
uv run pytest tests/test_criteria_cli.py -q
```

Expected: command exits non-zero because `criteria` is not registered as a Typer subgroup.

The first failure should show:

```text
No such command 'criteria'
```

- [ ] **Step 3: Keep red CLI tests uncommitted**

Run:

```bash
git status --short -- tests/test_criteria_cli.py
```

Expected:

```text
?? tests/test_criteria_cli.py
```

Do not stage or commit this file in Task 2. Commit it with the implementation in
Task 3 after the criteria CLI tests pass.

---

### Task 3: Implement Criteria Typer Subgroup

**Files:**
- Modify: `src/runlens/cli.py`

- [ ] **Step 1: Add helper imports and `write_spec` import**

Modify the imports in `src/runlens/cli.py` so they include these imports:

```python
from runlens.criteria import (
    CriteriaCommandError,
    add_criterion,
    reset_criterion,
    set_criterion_status,
)
```

Add `write_spec` to the existing `from runlens.store import (...)` block:

```python
    write_spec,
    write_state,
```

- [ ] **Step 2: Register the criteria Typer app**

Add this directly after the existing `app = typer.Typer(...)` line:

```python
criteria_app = typer.Typer(help="Maintain artifact_spec.yaml acceptance criteria.")
app.add_typer(criteria_app, name="criteria")
```

- [ ] **Step 3: Add criteria command wrappers**

Add these helpers after `_run_initialized_command`:

```python
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
```

- [ ] **Step 4: Add list command**

Add this command before `@app.command("init")`:

```python
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
```

- [ ] **Step 5: Add add command**

Add this command after `criteria_list_command`:

```python
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
```

- [ ] **Step 6: Add pass command**

Add this command after `criteria_add_command`:

```python
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
```

- [ ] **Step 7: Add fail command**

Add this command after `criteria_pass_command`:

```python
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
```

- [ ] **Step 8: Add reset command**

Add this command after `criteria_fail_command`:

```python
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
```

- [ ] **Step 9: Run CLI tests and verify GREEN**

Run:

```bash
uv run pytest tests/test_criteria_cli.py tests/test_criteria_helpers.py -q
```

Expected:

```text
18 passed
```

- [ ] **Step 10: Commit CLI implementation**

Run:

```bash
git add src/runlens/cli.py src/runlens/criteria.py tests/test_criteria_cli.py tests/test_criteria_helpers.py
git commit -m "feat: add criteria cli"
```

---

### Task 4: Full Regression And Closeout

**Files:**
- Modify only if verification exposes a real defect in the files from Tasks 1-3.

- [ ] **Step 1: Run full pytest suite**

Run:

```bash
uv run pytest -q
```

Expected:

```text
60 passed
```

- [ ] **Step 2: Verify root CLI help still works**

Run:

```bash
uv run runlens --help
```

Expected: command exits zero and includes these command names:

```text
criteria
init
update
render
checkpoint
finalize
```

- [ ] **Step 3: Verify criteria subgroup help**

Run:

```bash
uv run runlens criteria --help
```

Expected: command exits zero and includes:

```text
list
add
pass
fail
reset
```

- [ ] **Step 4: Run whitespace check**

Run:

```bash
git diff --check
```

Expected: no output and exit zero.

- [ ] **Step 5: Confirm worktree state**

Run:

```bash
git status --short --branch
```

Expected: branch is ahead by the implementation commits; `.codegraph/daemon.pid` may remain untracked and must not be staged.

- [ ] **Step 6: If fixes were needed during closeout, commit them**

If Task 4 required any code or test fixes, run:

```bash
git add src/runlens/cli.py src/runlens/criteria.py tests/test_criteria_cli.py tests/test_criteria_helpers.py
git commit -m "fix: harden criteria cli"
```

If Task 4 required no fixes, do not create an empty commit.

---

## Self-Review Checklist

- Spec coverage: every command in the Criteria UX design has a task and test.
- Boundary coverage: tests assert criteria commands do not mutate `run_state.json` or `RUN_STATE.md`.
- Duplicate safety: `criteria add` duplicate ID has a fixed error string and no YAML mutation.
- Gate safety: `criteria pass` rejects blank evidence and `finalize` remains an unchanged gate over required criteria.
- Scope safety: renderer, chart behavior, adapter docs, and service-class abstractions are not part of the plan.
