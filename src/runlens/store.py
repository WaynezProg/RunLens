from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import yaml

from runlens.models import (
    AcceptanceCriterion,
    ArtifactSpec,
    HistoryEntry,
    RunState,
    RunStatus,
    TaskInfo,
)


ARTIFACTS_DIR = ".agent-artifacts"
SPEC_FILE = "artifact_spec.yaml"
STATE_FILE = "run_state.json"
STATE_MARKDOWN = "RUN_STATE.md"
WORKING_REPORT = f"{ARTIFACTS_DIR}/working/report.html"


def now_utc() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def artifacts_root(base: Path) -> Path:
    return base / ARTIFACTS_DIR


def ensure_protocol_dirs(base: Path) -> None:
    root = artifacts_root(base)
    for path in (
        root / "working" / "data",
        root / "working" / "charts",
        root / "checkpoints",
        root / "deliverables",
    ):
        path.mkdir(parents=True, exist_ok=True)


def default_spec() -> ArtifactSpec:
    return ArtifactSpec(
        task=TaskInfo(
            title="RunLens task",
            description="Filesystem-first artifact protocol run",
        ),
        acceptance_criteria=[
            AcceptanceCriterion(
                id="define-criteria",
                description="Replace this placeholder with task-specific acceptance criteria.",
                status="pending",
                evidence=None,
                required=True,
            )
        ],
        artifacts=[],
        charts=[],
    )


def default_state() -> RunState:
    return RunState(
        state=RunStatus.working,
        note="Initialized RunLens artifacts.",
        last_report=WORKING_REPORT,
        updated_at=now_utc(),
        history=[],
    )


def write_spec(base: Path, spec: ArtifactSpec) -> None:
    ensure_protocol_dirs(base)
    path = artifacts_root(base) / SPEC_FILE
    payload = spec.model_dump(mode="json")
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def load_spec(base: Path) -> ArtifactSpec:
    path = artifacts_root(base) / SPEC_FILE
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    return ArtifactSpec.model_validate(payload)


def write_state(base: Path, state: RunState) -> None:
    ensure_protocol_dirs(base)
    root = artifacts_root(base)
    payload = state.model_dump(mode="json")
    (root / STATE_FILE).write_text(
        json.dumps(payload, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
    (root / STATE_MARKDOWN).write_text(render_state_markdown(state), encoding="utf-8")


def load_state(base: Path) -> RunState:
    path = artifacts_root(base) / STATE_FILE
    payload = json.loads(path.read_text(encoding="utf-8"))
    return RunState.model_validate(payload)


def render_state_markdown(state: RunState) -> str:
    last_report = state.last_report or "None"
    lines = [
        "# Run State",
        "",
        f"- State: {state.state}",
        f"- Updated At: {state.updated_at}",
        f"- Last Report: {last_report}",
        f"- Note: {state.note}",
        "",
        "## History",
        "",
    ]

    if state.history:
        for entry in state.history:
            lines.append(f"- {entry.updated_at}: {entry.state} - {entry.note}")
    else:
        lines.append("- No previous state.")

    lines.append("")
    return "\n".join(lines)


def init_artifacts(base: Path) -> None:
    ensure_protocol_dirs(base)
    write_spec(base, default_spec())
    write_state(base, default_state())


def update_state(
    base: Path,
    state: RunStatus | str,
    note: str,
    last_report: str | None = None,
) -> RunState:
    previous = load_state(base)
    history = [
        *previous.history,
        HistoryEntry(
            state=previous.state,
            note=previous.note,
            updated_at=previous.updated_at,
        ),
    ]
    next_state = RunState(
        state=state,
        note=note,
        last_report=last_report if last_report is not None else previous.last_report,
        updated_at=now_utc(),
        history=history,
    )
    write_state(base, next_state)
    return next_state
