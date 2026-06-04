from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


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
    required: bool = True

    @property
    def has_passing_evidence(self) -> bool:
        return self.status == "passed" and bool((self.evidence or "").strip())


class MetadataItem(StrictModel):
    path: str
    type: str
    title: str
    status: str


class ArtifactSpec(StrictModel):
    task: TaskInfo
    acceptance_criteria: list[AcceptanceCriterion] = Field(min_length=1)
    artifacts: list[MetadataItem] = Field(default_factory=list)
    charts: list[MetadataItem] = Field(default_factory=list)

    def required_criteria_passed(self) -> bool:
        return all(
            criterion.has_passing_evidence
            for criterion in self.acceptance_criteria
            if criterion.required
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
