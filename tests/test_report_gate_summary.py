"""v0.5.0 Report Gate UX: the working report must show, at a glance, whether the
finalize gate passes, which required criteria are unmet, and the current state.

These tests pin the summary to the *real* gate (`required_criteria_passed()`) so
the report can never claim "ready to finalize" when finalize would refuse.
"""

from __future__ import annotations

from pathlib import Path

from runlens.models import AcceptanceCriterion, ArtifactSpec, TaskInfo
from runlens.renderer import render_working_report
from runlens.store import init_artifacts, load_spec, update_state, write_spec


def _spec(criteria: list[AcceptanceCriterion]) -> ArtifactSpec:
    return ArtifactSpec(
        task=TaskInfo(title="T", description="D"),
        acceptance_criteria=criteria,
        artifacts=[],
        charts=[],
    )


def _crit(cid: str, status: str, evidence: str | None, required: bool) -> AcceptanceCriterion:
    return AcceptanceCriterion(
        id=cid, description=f"desc-{cid}", status=status, evidence=evidence, required=required
    )


def test_gate_summary_counts_and_unmet() -> None:
    summary = _spec(
        [
            _crit("a", "passed", "evi", required=True),
            _crit("b", "pending", None, required=True),
            _crit("c", "failed", "why", required=True),
            _crit("d", "pending", None, required=False),
        ]
    ).gate_summary()

    assert summary.required_total == 3
    assert (summary.passed, summary.pending, summary.failed) == (1, 1, 1)
    assert {u.id for u in summary.unmet_required} == {"b", "c"}
    assert summary.gate_passed is False


def test_gate_summary_pass_mirrors_required_criteria_passed() -> None:
    spec = _spec([_crit("a", "passed", "evi", required=True)])
    summary = spec.gate_summary()
    assert summary.gate_passed is spec.required_criteria_passed() is True
    assert summary.passed == 1 and not summary.unmet_required


def test_gate_summary_passed_without_evidence_is_unmet() -> None:
    summary = _spec([_crit("a", "passed", None, required=True)]).gate_summary()
    assert summary.gate_passed is False
    assert [u.reason for u in summary.unmet_required] == ["passed but missing evidence"]


def test_report_shows_fail_and_unmet_for_pending(isolated_cwd: Path) -> None:
    init_artifacts(isolated_cwd)  # default spec: required define-criteria is pending
    html = render_working_report(isolated_cwd).read_text()
    assert "Gate: FAIL" in html
    assert "define-criteria" in html
    assert "pending" in html.lower()


def test_report_shows_failed_criterion(isolated_cwd: Path) -> None:
    init_artifacts(isolated_cwd)
    spec = load_spec(isolated_cwd)
    failed = spec.acceptance_criteria[0].model_copy(
        update={"status": "failed", "evidence": "blocked by upstream"}
    )
    write_spec(isolated_cwd, spec.model_copy(update={"acceptance_criteria": [failed]}))

    html = render_working_report(isolated_cwd).read_text()
    assert "Gate: FAIL" in html
    assert "define-criteria" in html
    assert "failed" in html.lower()


def test_report_shows_blocked_reason(isolated_cwd: Path) -> None:
    init_artifacts(isolated_cwd)
    update_state(isolated_cwd, state="blocked", note="Missing production token")

    html = render_working_report(isolated_cwd).read_text()
    assert "Missing production token" in html
    assert "Gate: FAIL" in html


def test_report_shows_pass_when_required_met(isolated_cwd: Path) -> None:
    init_artifacts(isolated_cwd)
    spec = load_spec(isolated_cwd)
    passed = spec.acceptance_criteria[0].model_copy(
        update={"status": "passed", "evidence": "done"}
    )
    write_spec(isolated_cwd, spec.model_copy(update={"acceptance_criteria": [passed]}))

    html = render_working_report(isolated_cwd).read_text()
    assert "Gate: PASS" in html
