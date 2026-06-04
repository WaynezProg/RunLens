import json
from pathlib import Path

import yaml

from runlens.store import (
    ARTIFACTS_DIR,
    init_artifacts,
    load_spec,
    load_state,
    update_state,
)


def test_init_creates_protocol_tree_and_placeholder_criterion(isolated_cwd: Path):
    init_artifacts(isolated_cwd)

    root = isolated_cwd / ARTIFACTS_DIR
    assert (root / "artifact_spec.yaml").is_file()
    assert (root / "run_state.json").is_file()
    assert (root / "RUN_STATE.md").is_file()
    assert (root / "working" / "data").is_dir()
    assert (root / "working" / "charts").is_dir()
    assert (root / "checkpoints").is_dir()
    assert (root / "deliverables").is_dir()

    spec = yaml.safe_load((root / "artifact_spec.yaml").read_text())
    assert spec["acceptance_criteria"] == [
        {
            "id": "define-criteria",
            "description": "Replace this placeholder with task-specific acceptance criteria.",
            "status": "pending",
            "evidence": None,
            "required": True,
        }
    ]


def test_update_changes_state_files_but_not_acceptance_criteria(isolated_cwd: Path):
    init_artifacts(isolated_cwd)
    before_spec = (isolated_cwd / ARTIFACTS_DIR / "artifact_spec.yaml").read_text()

    state = update_state(isolated_cwd, state="working", note="implemented parser")

    assert state.state == "working"
    assert state.note == "implemented parser"
    assert load_state(isolated_cwd).note == "implemented parser"
    assert "implemented parser" in (isolated_cwd / ARTIFACTS_DIR / "RUN_STATE.md").read_text()
    assert (isolated_cwd / ARTIFACTS_DIR / "artifact_spec.yaml").read_text() == before_spec
    assert load_spec(isolated_cwd).acceptance_criteria[0].id == "define-criteria"


def test_run_state_json_does_not_copy_acceptance_criteria(isolated_cwd: Path):
    init_artifacts(isolated_cwd)

    raw_state = json.loads((isolated_cwd / ARTIFACTS_DIR / "run_state.json").read_text())

    assert "acceptance_criteria" not in raw_state
