# Proactive HTML Delivery on Agent Stop — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** On agent `Stop`, automatically refresh the working HTML report and — only when the acceptance gate already passes — write the final deliverable, for every agent that fires a Stop hook.

**Architecture:** All four agents' hooks call the same `runlens hook` command. Add the Stop→HTML logic in one shared place: a new `runlens.autoreport.emit_report_on_stop(project_dir)` function invoked from the `hook` command's Stop branch. It reuses the existing `store`/`renderer` primitives and the `ArtifactSpec.required_criteria_passed()` gate — no duplicated gate logic — and never raises (best-effort telemetry).

**Tech Stack:** Python 3.13, Typer, Pydantic, Jinja2, pytest, `uv`.

---

## File Structure

- Create: `src/runlens/autoreport.py` — the Stop→HTML composition (`emit_report_on_stop`, `ReportOutcome`). One responsibility: given a project dir, refresh the working report and conditionally finalize.
- Modify: `src/runlens/cli.py:341-348` — `hook_command` calls `emit_report_on_stop` on Stop and logs a synthetic `report` event.
- Create: `tests/test_autoreport.py` — unit tests for `emit_report_on_stop`.
- Modify: `tests/test_hook.py` — integration tests for Stop-triggered rendering via the CLI.
- Modify: `examples/adapters/opencode/runlens-artifact-protocol/SKILL.md` — the "content half": tell agents to `init` early and keep the spec truthful.
- Modify: `docs/hook-adapter.md` — document the new Stop behavior and the honest per-agent matrix.

**Already landed (do not redo):** `scripts/runlens-hook` is now fail-safe (always exit 0, PATH-robust, silent stdout) and reinstalled; `tests/test_hook_wrapper.py` covers it. The autoreport change is pure Python picked up by `uv run runlens hook` — no reinstall needed.

---

### Task 1: `emit_report_on_stop` composition function

**Files:**
- Create: `src/runlens/autoreport.py`
- Test: `tests/test_autoreport.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_autoreport.py`:

```python
from pathlib import Path

from runlens.autoreport import emit_report_on_stop
from runlens.models import AcceptanceCriterion
from runlens.store import ARTIFACTS_DIR, init_artifacts, load_spec, load_state, write_spec


def _set_required(base: Path, *, status: str, evidence: str | None) -> None:
    spec = load_spec(base)
    spec.acceptance_criteria = [
        AcceptanceCriterion(
            id="done",
            description="Work complete",
            status=status,
            evidence=evidence,
            required=True,
        )
    ]
    write_spec(base, spec)


def test_no_artifacts_is_noop(tmp_path: Path):
    outcome = emit_report_on_stop(tmp_path)
    assert outcome.skipped_no_artifacts is True
    assert outcome.rendered is False
    assert not (tmp_path / ARTIFACTS_DIR).exists()


def test_renders_working_when_criteria_not_passed(tmp_path: Path):
    init_artifacts(tmp_path)  # seeds a pending required placeholder
    outcome = emit_report_on_stop(tmp_path)
    assert outcome.rendered is True
    assert outcome.finalized is False
    assert (tmp_path / ARTIFACTS_DIR / "working" / "report.html").exists()
    assert not (tmp_path / ARTIFACTS_DIR / "deliverables" / "final.html").exists()
    assert load_state(tmp_path).state != "final"


def test_renders_and_finalizes_when_criteria_pass(tmp_path: Path):
    init_artifacts(tmp_path)
    _set_required(tmp_path, status="passed", evidence="uv run pytest -q: passed")
    outcome = emit_report_on_stop(tmp_path)
    assert outcome.rendered is True
    assert outcome.finalized is True
    final_html = tmp_path / ARTIFACTS_DIR / "deliverables" / "final.html"
    assert final_html.exists()
    assert "Work complete" in final_html.read_text()
    assert load_state(tmp_path).state == "final"


def test_already_final_does_not_refinalize(tmp_path: Path):
    init_artifacts(tmp_path)
    _set_required(tmp_path, status="passed", evidence="ok")
    first = emit_report_on_stop(tmp_path)
    assert first.finalized is True
    stamp = load_state(tmp_path).updated_at

    second = emit_report_on_stop(tmp_path)
    assert second.rendered is True
    assert second.finalized is False
    assert load_state(tmp_path).updated_at == stamp  # no new state transition


def test_invalid_spec_returns_error_without_raising(tmp_path: Path):
    init_artifacts(tmp_path)
    (tmp_path / ARTIFACTS_DIR / "artifact_spec.yaml").write_text(
        "acceptance_criteria: [oops\n", encoding="utf-8"
    )
    outcome = emit_report_on_stop(tmp_path)  # must not raise
    assert outcome.error is not None
    assert outcome.rendered is False
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_autoreport.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'runlens.autoreport'`.

- [ ] **Step 3: Implement `autoreport.py`**

Create `src/runlens/autoreport.py`:

```python
"""Stop-triggered HTML emission: refresh the working report and, when the
acceptance gate already passes, write the final deliverable.

Best-effort by contract — this runs from a lifecycle hook and must NEVER raise.
It reuses the same primitives and gate predicate as `runlens finalize`; it adds
no divergent gate logic.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from runlens.models import RunStatus
from runlens.renderer import (
    final_report_path,
    render_final_report,
    render_working_report,
)
from runlens.store import (
    SPEC_FILE,
    artifacts_root,
    build_updated_state,
    load_spec,
    load_state,
    write_state,
)

_FINAL_NOTE = "All required acceptance criteria passed."


@dataclass(frozen=True)
class ReportOutcome:
    rendered: bool = False
    finalized: bool = False
    working_report: str | None = None
    final_report: str | None = None
    skipped_no_artifacts: bool = False
    error: str | None = None

    def as_event_payload(self) -> dict:
        return {
            "rendered": self.rendered,
            "finalized": self.finalized,
            "working_report": self.working_report,
            "final_report": self.final_report,
            "skipped_no_artifacts": self.skipped_no_artifacts,
            "error": self.error,
        }


def _brief(exc: Exception) -> str:
    text = str(exc).strip().splitlines()
    return text[0] if text else exc.__class__.__name__


def _already_final(project_dir: Path) -> bool:
    if not final_report_path(project_dir).exists():
        return False
    try:
        return str(load_state(project_dir).state) == RunStatus.final.value
    except Exception:  # noqa: BLE001 - best-effort
        return False


def emit_report_on_stop(project_dir: Path) -> ReportOutcome:
    """Refresh the working report; finalize only when the gate already passes.

    Never raises. Skips entirely when the project has no artifact spec.
    """
    if not (artifacts_root(project_dir) / SPEC_FILE).exists():
        return ReportOutcome(skipped_no_artifacts=True)

    try:
        spec = load_spec(project_dir)
        working = render_working_report(project_dir)
    except Exception as exc:  # noqa: BLE001 - best-effort telemetry
        return ReportOutcome(error=_brief(exc))

    working_rel = working.relative_to(project_dir).as_posix()

    # Same predicate `finalize` uses. Only finalize when it will succeed —
    # finalize-on-fail sets state `failed` and deletes final.html.
    if not spec.required_criteria_passed() or _already_final(project_dir):
        return ReportOutcome(rendered=True, working_report=working_rel)

    try:
        final_report = final_report_path(project_dir)
        state = build_updated_state(
            project_dir,
            state=RunStatus.final,
            note=_FINAL_NOTE,
            last_report=final_report.relative_to(project_dir).as_posix(),
        )
        output = render_final_report(project_dir, state=state)
        write_state(project_dir, state)
    except Exception as exc:  # noqa: BLE001 - best-effort
        return ReportOutcome(rendered=True, working_report=working_rel, error=_brief(exc))

    return ReportOutcome(
        rendered=True,
        finalized=True,
        working_report=working_rel,
        final_report=output.relative_to(project_dir).as_posix(),
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_autoreport.py -q`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add src/runlens/autoreport.py tests/test_autoreport.py
git commit -m "feat: add emit_report_on_stop for Stop-triggered HTML"
```

---

### Task 2: Wire `emit_report_on_stop` into the `hook` command

**Files:**
- Modify: `src/runlens/cli.py:341-348` (the `hook_command`)
- Test: `tests/test_hook.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_hook.py`:

```python
def test_hook_stop_renders_and_logs_report_event(
    isolated_cwd: Path, monkeypatch, tmp_path: Path
):
    """Stop on a gate-passing project renders + finalizes and logs a `report`
    event alongside the lifecycle `Stop` event."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    runner = CliRunner()
    runner.invoke(cli_app, ["init"])
    # Pass the seeded required placeholder so the gate is satisfied.
    runner.invoke(
        cli_app,
        ["criteria", "pass", "--id", "define-criteria", "--evidence", "done"],
    )

    result = runner.invoke(
        cli_app, ["hook", "--event", "Stop", "--agent", "claude-code"], input="{}"
    )
    assert result.exit_code == 0, result.output
    assert result.output == ""

    from runlens.store import ARTIFACTS_DIR
    assert (isolated_cwd / ARTIFACTS_DIR / "deliverables" / "final.html").exists()

    jsonl = tmp_path / "runlens" / "hooks.jsonl"
    events = [json.loads(line) for line in jsonl.read_text().strip().splitlines()]
    names = [e["event"] for e in events]
    assert "Stop" in names
    assert "report" in names
    report = next(e for e in events if e["event"] == "report")
    assert report["raw"]["finalized"] is True
    assert report["raw"]["final_report"].endswith("deliverables/final.html")


def test_hook_stop_without_artifacts_logs_only_lifecycle(
    isolated_cwd: Path, monkeypatch, tmp_path: Path
):
    """Stop in a repo that never used RunLens logs only the lifecycle event."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    runner = CliRunner()
    result = runner.invoke(
        cli_app, ["hook", "--event", "Stop", "--agent", "cursor"], input="{}"
    )
    assert result.exit_code == 0, result.output

    jsonl = tmp_path / "runlens" / "hooks.jsonl"
    events = [json.loads(line) for line in jsonl.read_text().strip().splitlines()]
    assert [e["event"] for e in events] == ["Stop"]


def test_hook_non_stop_event_does_not_render(
    isolated_cwd: Path, monkeypatch, tmp_path: Path
):
    """Only Stop triggers rendering; SessionStart must not write a report."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    runner = CliRunner()
    runner.invoke(cli_app, ["init"])

    result = runner.invoke(
        cli_app, ["hook", "--event", "SessionStart", "--agent", "claude-code"], input="{}"
    )
    assert result.exit_code == 0, result.output

    from runlens.store import ARTIFACTS_DIR
    assert not (isolated_cwd / ARTIFACTS_DIR / "working" / "report.html").exists()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_hook.py -q`
Expected: FAIL — `test_hook_stop_renders_and_logs_report_event` finds no `report` event / no `final.html`.

- [ ] **Step 3: Modify `hook_command`**

In `src/runlens/cli.py`, add the import near the other `runlens` imports (after line 19):

```python
from runlens.autoreport import emit_report_on_stop
```

Replace the body of `hook_command` (currently `cli.py:341-348`) with:

```python
@app.command("hook")
def hook_command(
    event: str = typer.Option(..., "--event", help="Event name (e.g. SessionStart)"),
    agent: str = typer.Option(..., "--agent", help="Agent runtime (claude-code|codex|opencode|cursor)"),
) -> None:
    """Normalize a lifecycle event and append to hooks.jsonl.

    On `Stop`, additionally refresh the working report and — when the gate
    already passes — write the final deliverable, logging a `report` event.
    Best-effort: never fails the hook.
    """
    stdin_data = sys.stdin.read()
    normalize_and_append(event=event, agent=agent, stdin_data=stdin_data)

    if event == "Stop":
        try:
            outcome = emit_report_on_stop(Path.cwd())
        except Exception:  # noqa: BLE001 - hook must never crash the agent
            return
        if outcome.rendered or outcome.error:
            normalize_and_append(
                event="report",
                agent=agent,
                stdin_data=json.dumps(outcome.as_event_payload()),
            )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_hook.py -q`
Expected: PASS (all hook tests, old and new).

- [ ] **Step 5: Commit**

```bash
git add src/runlens/cli.py tests/test_hook.py
git commit -m "feat: render and conditionally finalize on Stop hook"
```

---

### Task 3: Strengthen the skill (content half)

**Files:**
- Modify: `examples/adapters/opencode/runlens-artifact-protocol/SKILL.md`

- [ ] **Step 1: Add a "Proactive delivery" section**

After the `## Commands` section (before `## Do Not`), insert:

```markdown
## Proactive delivery (how HTML gets produced)

The RunLens Stop hook auto-produces HTML when a session ends — but only from
what you recorded. To make the deliverable worth reading:

- Run `uv run runlens init` at the **start** of deliverable work so
  `.agent-artifacts/` exists. With no spec, the Stop hook has nothing to render.
- Record criteria and progress as you go (`criteria add` / `criteria pass`
  with real evidence, `update --note`). The Stop hook re-renders the working
  report and, once every required criterion passes with evidence, writes
  `deliverables/final.html` for you.
- You do **not** need to run `render` manually — the Stop hook does it. Your job
  is to keep `artifact_spec.yaml` truthful.
```

- [ ] **Step 2: Verify it reads coherently**

Run: `git diff examples/adapters/opencode/runlens-artifact-protocol/SKILL.md`
Expected: only the new section added; surrounding content intact.

- [ ] **Step 3: Commit**

```bash
git add examples/adapters/opencode/runlens-artifact-protocol/SKILL.md
git commit -m "docs: skill explains Stop-hook proactive HTML delivery"
```

Note: the deployed copy at `~/.claude/skills/runlens-artifact-protocol/SKILL.md` is a separate install; re-deploying it is a manual step outside this repo and is out of scope for this plan.

---

### Task 4: Update hook-adapter docs

**Files:**
- Modify: `docs/hook-adapter.md`

- [ ] **Step 1: Add a "Stop behavior" subsection**

Under `## Purpose` (after the bullet list ending with the `runlens ingest` line), add:

```markdown
### Stop → HTML delivery

On a `Stop` event, the hook does more than log: if the event's working
directory contains `.agent-artifacts/`, it refreshes the working HTML report,
and — only when every required acceptance criterion already passes with
evidence — writes `deliverables/final.html`. The finalize gate is checked
*before* finalizing, so an incomplete session never flips the run to `failed`.
A synthetic `report` event records what was produced. Projects without
`.agent-artifacts/` are untouched.
```

- [ ] **Step 2: Correct the runtime-verification table**

Replace the Cursor row and surrounding honesty notes in the
"Runtime Verification Status" table so it reads (Codex/Cursor are best-effort):

```markdown
| Agent     | Installer | Direct-Call Verified | Runtime Verified |
|-----------|-----------|----------------------|------------------|
| Claude Code | ✓       | ✓                    | ✓                |
| OpenCode    | ✓       | ✓                    | ✓                |
| Codex       | ✓       | ✓                    | ⚠ one-time `/hooks trust` required |
| Cursor      | ✓       | ✓                    | ⚠ IDE only — `cursor-agent` CLI does not fire `stop` |
```

- [ ] **Step 3: Verify the rendered markdown**

Run: `git diff docs/hook-adapter.md`
Expected: the new subsection plus the corrected table; no unrelated edits.

- [ ] **Step 4: Commit**

```bash
git add docs/hook-adapter.md
git commit -m "docs: document Stop->HTML behavior and honest agent matrix"
```

---

### Task 5: Full verification + live smoke

**Files:** none (verification only)

- [ ] **Step 1: Run the whole suite**

Run: `uv run pytest -q`
Expected: PASS — all prior tests plus the new `test_autoreport.py` and the three new hook tests.

- [ ] **Step 2: Whitespace lint**

Run: `git diff --check`
Expected: no output.

- [ ] **Step 3: Live smoke on a throwaway project**

```bash
tmp=$(mktemp -d); cd "$tmp"
uv run --project /Users/waynetu/claw_prog/projects/04-kurisu-github/RunLens runlens init
uv run --project /Users/waynetu/claw_prog/projects/04-kurisu-github/RunLens runlens criteria pass --id define-criteria --evidence "smoke"
echo '{}' | ~/.local/bin/runlens-hook --event Stop --agent claude-code
ls .agent-artifacts/deliverables/final.html && echo "FINAL WRITTEN"
cd - && rm -rf "$tmp"
```

Expected: `final.html` exists ("FINAL WRITTEN" printed); a `report` event appears in `~/.local/share/runlens/hooks.jsonl`.

- [ ] **Step 4 (optional): Live confirm on Claude + OpenCode**

Run a trivial `opencode run` and a Claude turn in an initialized project; confirm a `report` event with the produced paths appears in `hooks.jsonl`. Leave Codex (needs one-time `/hooks trust`) and Cursor (IDE only) as best-effort — do not chase their CLI firing.

---

## Self-Review

- **Spec coverage:** one shared choke point (Task 2) ✓; render-always + conditional-finalize + already-final skip (Task 1) ✓; gate-before-finalize safety (Task 1 code + test) ✓; never-raises (Task 1 error test + Task 2 guard) ✓; synthetic `report` event (Task 2) ✓; skill content-half (Task 3) ✓; honest per-agent matrix (Task 4) ✓; wrapper fail-safe (already landed, noted) ✓; testing matrix (Tasks 1–2, 5) ✓.
- **Placeholder scan:** no TBD/TODO; all code shown in full. The deliberately-flagged stray `spec_path` local in Task 2's test is called out for removal.
- **Type consistency:** `ReportOutcome` fields and `as_event_payload()` keys match between Task 1 (definition) and Task 2 (usage: `outcome.rendered`, `outcome.error`, `as_event_payload()`). `emit_report_on_stop(project_dir)` signature consistent across tasks. State comparison uses the stored string value (`== "final"` / `RunStatus.final.value`), matching existing finalize tests.
