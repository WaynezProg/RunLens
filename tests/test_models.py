import pytest
from pydantic import ValidationError

from runlens.models import (
    AcceptanceCriterion,
    ArtifactSpec,
    MetadataItem,
    RunState,
    TaskInfo,
)


def test_acceptance_criterion_allows_required_pending_placeholder():
    criterion = AcceptanceCriterion(
        id="define-criteria",
        description="Replace this placeholder with task-specific acceptance criteria.",
        status="pending",
        evidence=None,
        required=True,
    )

    assert criterion.id == "define-criteria"
    assert criterion.status == "pending"
    assert criterion.evidence is None
    assert criterion.required is True


def test_acceptance_criterion_rejects_unknown_status():
    with pytest.raises(ValidationError):
        AcceptanceCriterion(
            id="bad",
            description="Bad status",
            status="done",
            evidence="notes",
            required=True,
        )


def test_acceptance_criterion_rejects_non_boolean_required():
    with pytest.raises(ValidationError):
        AcceptanceCriterion(
            id="bad-required",
            description="Bad required type",
            status="pending",
            evidence=None,
            required="true",
        )


def test_artifact_spec_requires_at_least_one_criterion():
    with pytest.raises(ValidationError):
        ArtifactSpec(
            task=TaskInfo(title="Task", description="Description"),
            acceptance_criteria=[],
            artifacts=[],
            charts=[],
        )


def test_metadata_item_rejects_large_inline_fields():
    with pytest.raises(ValidationError):
        MetadataItem(
            path="working/report.html",
            type="html",
            title="Report",
            status="ready",
            html="<p>inline body is not allowed</p>",
        )


def test_run_state_rejects_unknown_state():
    with pytest.raises(ValidationError):
        RunState(
            state="done",
            note="Bad state",
            last_report=None,
            updated_at="2026-06-04T00:00:00Z",
            history=[],
        )
