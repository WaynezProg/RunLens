from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool


CriterionStatus = Literal["pending", "passed", "failed"]


class RunStatus(str, Enum):
    working = "working"
    checkpoint = "checkpoint"
    blocked = "blocked"
    failed = "failed"
    final = "final"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=True)


class TaskInfo(StrictModel):
    title: str
    description: str


class AcceptanceCriterion(StrictModel):
    id: str
    description: str
    status: CriterionStatus
    evidence: str | None = None
    required: StrictBool = True

    @property
    def has_passing_evidence(self) -> bool:
        return self.status == "passed" and bool((self.evidence or "").strip())


class MetadataItem(StrictModel):
    path: str
    type: str
    title: str
    status: str


@dataclass(frozen=True)
class UnmetCriterion:
    id: str
    description: str
    status: str
    reason: str


@dataclass(frozen=True)
class GateSummary:
    """Presentation-only view of the finalize gate; never persisted."""

    gate_passed: bool
    required_total: int
    passed: int
    pending: int
    failed: int
    unmet_required: list[UnmetCriterion] = field(default_factory=list)


class ArtifactSpec(StrictModel):
    task: TaskInfo
    acceptance_criteria: list[AcceptanceCriterion] = Field(min_length=1)
    artifacts: list[MetadataItem] = Field(default_factory=list)
    charts: list[MetadataItem] = Field(default_factory=list)

    def required_criteria_passed(self) -> bool:
        required_criteria = [
            criterion for criterion in self.acceptance_criteria if criterion.required
        ]
        return bool(required_criteria) and all(
            criterion.has_passing_evidence for criterion in required_criteria
        )

    def gate_summary(self) -> GateSummary:
        """Derive a readable gate verdict. PASS/FAIL mirrors the real gate exactly."""
        required = [c for c in self.acceptance_criteria if c.required]
        unmet: list[UnmetCriterion] = []
        for criterion in required:
            if criterion.has_passing_evidence:
                continue
            if criterion.status == "passed":
                reason = "passed but missing evidence"
            elif criterion.status == "failed":
                reason = "marked failed"
            else:
                reason = "pending"
            unmet.append(
                UnmetCriterion(
                    id=criterion.id,
                    description=criterion.description,
                    status=criterion.status,
                    reason=reason,
                )
            )
        return GateSummary(
            gate_passed=self.required_criteria_passed(),
            required_total=len(required),
            passed=sum(1 for c in required if c.status == "passed"),
            pending=sum(1 for c in required if c.status == "pending"),
            failed=sum(1 for c in required if c.status == "failed"),
            unmet_required=unmet,
        )


class HistoryEntry(StrictModel):
    state: RunStatus
    note: str
    updated_at: str


class RunState(StrictModel):
    state: RunStatus
    note: str
    last_report: str | None = None
    updated_at: str
    history: list[HistoryEntry] = Field(default_factory=list)
