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
