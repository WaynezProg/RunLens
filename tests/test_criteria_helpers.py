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
