# Artifact Watch Autorender (Tier 3) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `runlens watch` — a foreground, stdlib-only poll loop that debounce-renders `working/report.html` when `artifact_spec.yaml` or `run_state.json` change, without ever auto-finalizing.

**Architecture:** New `runlens.autorender` module owns (1) a testable debounce controller, (2) `emit_working_report_on_change` (render-only, never raises, never writes `final.html`), and (3) `watch_artifacts` polling loop using file mtimes. The CLI `watch` command is a thin Typer wrapper. No new dependencies; no SessionStart background daemon in this plan (YAGNI — orphan-process risk).

**Tech Stack:** Python 3.13 stdlib (`time`, `pathlib`), existing `store` + `renderer`, Typer, pytest, `uv`.

**Design spec:** `docs/superpowers/specs/2026-06-06-html-delivery-trigger-strategy-design.md` (Tier 3)

---

## File Structure

- Create: `src/runlens/autorender.py` — debounce controller, emit function, watch loop
- Modify: `src/runlens/cli.py` — add `watch` command
- Create: `tests/test_autorender.py` — unit tests (debounce + emit + never-finalize)
- Create: `tests/test_watch_cli.py` — CLI smoke + threaded integration
- Modify: `examples/adapters/opencode/runlens-artifact-protocol/SKILL.md` — Tier 3 from "planned" → available
- Modify: `docs/hook-adapter.md` — mention `runlens watch` as Tier 3 option
- Modify: `AGENTS.md`, `CLAUDE.md` — add `runlens watch` to command list (one line each)

**Explicit non-goals (this plan):**

- Auto-finalize on artifact change
- `watchdog` or other third-party file watchers
- SessionStart background `watch` spawn (document as future idea only)
- Watching files other than `artifact_spec.yaml` and `run_state.json`

---

### Task 1: Debounce controller

**Files:**
- Create: `src/runlens/autorender.py` (partial — controller only)
- Test: `tests/test_autorender.py` (partial — controller tests)

- [ ] **Step 1: Write the failing controller tests**

Create `tests/test_autorender.py`:

```python
from runlens.autorender import ArtifactWatchController


def test_debounce_waits_quiet_period():
    clock = [0.0]

    def monotonic() -> float:
        return clock[0]

    ctrl = ArtifactWatchController(debounce_seconds=2.0, monotonic=monotonic)
    ctrl.observe_change(0.0)
    clock[0] = 1.5
    assert ctrl.should_render() is False
    clock[0] = 2.0
    assert ctrl.should_render() is False
    clock[0] = 2.01
    assert ctrl.should_render() is True


def test_debounce_coalesces_rapid_changes():
    clock = [0.0]

    def monotonic() -> float:
        return clock[0]

    ctrl = ArtifactWatchController(debounce_seconds=2.0, monotonic=monotonic)
    ctrl.observe_change(0.0)
    clock[0] = 0.5
    ctrl.observe_change()
    clock[0] = 1.0
    ctrl.observe_change()
    clock[0] = 2.5
    assert ctrl.should_render() is False  # only 1.5s since last change at 1.0
    clock[0] = 3.01
    assert ctrl.should_render() is True


def test_should_render_is_false_when_no_change():
    ctrl = ArtifactWatchController(debounce_seconds=2.0, monotonic=lambda: 100.0)
    assert ctrl.should_render() is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_autorender.py -v`
Expected: FAIL — `ModuleNotFoundError: runlens.autorender`

- [ ] **Step 3: Implement `ArtifactWatchController`**

Add to `src/runlens/autorender.py`:

```python
from __future__ import annotations

import time
from collections.abc import Callable


class ArtifactWatchController:
    """Debounce artifact-file changes before triggering a render."""

    def __init__(
        self,
        debounce_seconds: float,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._debounce_seconds = debounce_seconds
        self._monotonic = monotonic
        self._change_at: float | None = None

    def observe_change(self, at: float | None = None) -> None:
        self._change_at = at if at is not None else self._monotonic()

    def should_render(self, at: float | None = None) -> bool:
        now = at if at is not None else self._monotonic()
        if self._change_at is None:
            return False
        if now - self._change_at < self._debounce_seconds:
            return False
        self._change_at = None
        return True
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_autorender.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add src/runlens/autorender.py tests/test_autorender.py
git commit -m "feat: add ArtifactWatchController for debounced autorender"
```

---

### Task 2: `emit_working_report_on_change` (render-only, never raises)

**Files:**
- Modify: `src/runlens/autorender.py`
- Modify: `tests/test_autorender.py`

- [ ] **Step 1: Write the failing emit tests**

Append to `tests/test_autorender.py`:

```python
from pathlib import Path

from runlens.autorender import emit_working_report_on_change
from runlens.models import AcceptanceCriterion
from runlens.store import ARTIFACTS_DIR, init_artifacts, load_spec, write_spec


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


def test_emit_skips_when_no_artifacts(tmp_path: Path):
    outcome = emit_working_report_on_change(tmp_path)
    assert outcome.skipped_no_artifacts is True
    assert outcome.rendered is False


def test_emit_renders_working_report(tmp_path: Path):
    init_artifacts(tmp_path)
    outcome = emit_working_report_on_change(tmp_path)
    assert outcome.rendered is True
    assert outcome.working_report == f"{ARTIFACTS_DIR}/working/report.html"
    assert (tmp_path / ARTIFACTS_DIR / "working" / "report.html").exists()


def test_emit_never_writes_final_html_even_when_gate_passes(tmp_path: Path):
    init_artifacts(tmp_path)
    _set_required(tmp_path, status="passed", evidence="uv run pytest -q: passed")
    outcome = emit_working_report_on_change(tmp_path)
    assert outcome.rendered is True
    assert not (tmp_path / ARTIFACTS_DIR / "deliverables" / "final.html").exists()


def test_emit_invalid_spec_returns_error_without_raising(tmp_path: Path):
    init_artifacts(tmp_path)
    (tmp_path / ARTIFACTS_DIR / "artifact_spec.yaml").write_text(
        "acceptance_criteria: [oops\n", encoding="utf-8"
    )
    outcome = emit_working_report_on_change(tmp_path)
    assert outcome.error is not None
    assert outcome.rendered is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_autorender.py::test_emit_skips_when_no_artifacts -v`
Expected: FAIL — `cannot import name 'emit_working_report_on_change'`

- [ ] **Step 3: Implement emit function and outcome**

Append to `src/runlens/autorender.py`:

```python
from dataclasses import dataclass
from pathlib import Path

from runlens.renderer import render_working_report
from runlens.store import SPEC_FILE, artifacts_root


@dataclass(frozen=True)
class AutorenderOutcome:
    rendered: bool = False
    working_report: str | None = None
    skipped_no_artifacts: bool = False
    error: str | None = None


def _brief(exc: Exception) -> str:
    text = str(exc).strip().splitlines()
    return text[0] if text else exc.__class__.__name__


def emit_working_report_on_change(project_dir: Path) -> AutorenderOutcome:
    """Render working/report.html only. Never finalize. Never raises."""
    if not (artifacts_root(project_dir) / SPEC_FILE).exists():
        return AutorenderOutcome(skipped_no_artifacts=True)

    try:
        working = render_working_report(project_dir)
    except Exception as exc:  # noqa: BLE001 - best-effort
        return AutorenderOutcome(error=_brief(exc))

    return AutorenderOutcome(
        rendered=True,
        working_report=working.relative_to(project_dir).as_posix(),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_autorender.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add src/runlens/autorender.py tests/test_autorender.py
git commit -m "feat: add emit_working_report_on_change (render-only autorender)"
```

---

### Task 3: `watch_artifacts` poll loop

**Files:**
- Modify: `src/runlens/autorender.py`
- Modify: `tests/test_autorender.py`

- [ ] **Step 1: Write failing watch-path and loop tests**

Append to `tests/test_autorender.py`:

```python
import threading

from runlens.autorender import artifact_watch_paths, watch_artifacts
from runlens.store import SPEC_FILE, STATE_FILE, init_artifacts, update_state
from runlens.models import RunStatus


def test_artifact_watch_paths(tmp_path: Path):
    init_artifacts(tmp_path)
    spec_path, state_path = artifact_watch_paths(tmp_path)
    assert spec_path.name == SPEC_FILE
    assert state_path.name == STATE_FILE
    assert spec_path.exists()
    assert state_path.exists()


def test_watch_renders_after_debounced_state_change(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    init_artifacts(tmp_path)
    report = tmp_path / ARTIFACTS_DIR / "working" / "report.html"
    report.unlink()

    stop = threading.Event()

    def run_watch() -> None:
        watch_artifacts(
            tmp_path,
            debounce_seconds=0.1,
            poll_interval_seconds=0.05,
            stop_event=stop,
        )

    thread = threading.Thread(target=run_watch, daemon=True)
    thread.start()
    try:
        update_state(tmp_path, state=RunStatus.working, note="watch test")
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            if report.exists():
                break
            time.sleep(0.05)
        assert report.exists()
        assert "watch test" in report.read_text()
    finally:
        stop.set()
        thread.join(timeout=2.0)
```

Add `import time` at top of test file.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_autorender.py::test_watch_renders_after_debounced_state_change -v`
Expected: FAIL — `cannot import name 'watch_artifacts'`

- [ ] **Step 3: Implement paths + watch loop**

Append to `src/runlens/autorender.py`:

```python
import time
from threading import Event

from runlens.store import STATE_FILE, artifacts_root


def artifact_watch_paths(project_dir: Path) -> tuple[Path, Path]:
    root = artifacts_root(project_dir)
    return root / SPEC_FILE, root / STATE_FILE


def _mtime_snapshot(paths: tuple[Path, ...]) -> tuple[int, ...]:
    return tuple(path.stat().st_mtime_ns if path.exists() else 0 for path in paths)


def watch_artifacts(
    project_dir: Path,
    *,
    debounce_seconds: float = 2.0,
    poll_interval_seconds: float = 0.25,
    stop_event: Event | None = None,
) -> None:
    """Poll artifact spec/state mtimes; debounce-render working report. Blocks until stop."""
    paths = artifact_watch_paths(project_dir)
    if not paths[0].exists():
        msg = f"Missing {SPEC_FILE}; run `runlens init` first."
        raise FileNotFoundError(msg)

    controller = ArtifactWatchController(debounce_seconds=debounce_seconds)
    last_seen = _mtime_snapshot(paths)

    while stop_event is None or not stop_event.is_set():
        time.sleep(poll_interval_seconds)
        current = _mtime_snapshot(paths)
        if current != last_seen:
            last_seen = current
            controller.observe_change()
        if controller.should_render():
            emit_working_report_on_change(project_dir)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_autorender.py -v`
Expected: PASS (9 tests)

- [ ] **Step 5: Commit**

```bash
git add src/runlens/autorender.py tests/test_autorender.py
git commit -m "feat: add watch_artifacts poll loop with debounced render"
```

---

### Task 4: `runlens watch` CLI command

**Files:**
- Modify: `src/runlens/cli.py`
- Create: `tests/test_watch_cli.py`

- [ ] **Step 1: Write failing CLI tests**

Create `tests/test_watch_cli.py`:

```python
from pathlib import Path

from runlens.cli import app as cli_app
from typer.testing import CliRunner

from runlens.store import ARTIFACTS_DIR


def test_watch_requires_init(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli_app, ["watch", "--debounce", "0.1", "--poll-interval", "0.05"])
    assert result.exit_code != 0
    assert "init" in result.stderr.lower() or "init" in result.stdout.lower()


def test_watch_help_lists_options():
    runner = CliRunner()
    result = runner.invoke(cli_app, ["watch", "--help"])
    assert result.exit_code == 0
    assert "--debounce" in result.stdout
    assert "--poll-interval" in result.stdout
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_watch_cli.py -v`
Expected: FAIL — unknown command `watch`

- [ ] **Step 3: Add `watch` command to `cli.py`**

Add import:

```python
from runlens.autorender import watch_artifacts
```

Add command (place after `render_command`, before `finalize_command`):

```python
@app.command("watch")
def watch_command(
    debounce: float = typer.Option(
        2.0,
        "--debounce",
        help="Seconds of quiet time after the last artifact change before rendering.",
    ),
    poll_interval: float = typer.Option(
        0.25,
        "--poll-interval",
        help="Seconds between mtime polls.",
    ),
) -> None:
    """Poll artifact spec/state and debounce-render the working HTML report."""

    def run_watch() -> None:
        try:
            watch_artifacts(
                Path.cwd(),
                debounce_seconds=debounce,
                poll_interval_seconds=poll_interval,
            )
        except KeyboardInterrupt:
            raise typer.Exit(0) from None

    _run_initialized_command(run_watch)
    typer.echo("Stopped watching.")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_watch_cli.py tests/test_autorender.py -v`
Expected: PASS

- [ ] **Step 5: Run full suite**

Run: `uv run pytest -q`
Expected: all tests pass

- [ ] **Step 6: Commit**

```bash
git add src/runlens/cli.py tests/test_watch_cli.py
git commit -m "feat: add runlens watch CLI for Tier 3 autorender"
```

---

### Task 5: Documentation and skill alignment

**Files:**
- Modify: `examples/adapters/opencode/runlens-artifact-protocol/SKILL.md`
- Modify: `docs/hook-adapter.md`
- Modify: `docs/superpowers/specs/2026-06-06-html-delivery-trigger-strategy-design.md`
- Modify: `AGENTS.md`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Update skill Tier 3 section**

In `examples/adapters/opencode/runlens-artifact-protocol/SKILL.md`, replace the Tier 3 paragraph with:

```markdown
### Tier 3 — Artifact watch (optional automation)

In a separate terminal, run:

```bash
uv run runlens watch
```

This polls `artifact_spec.yaml` and `run_state.json` and debounce-renders
`working/report.html` (~2s after the last change). It **never** writes
`final.html`. Tier 1 explicit `render` / `finalize` still apply at closeout.
```

- [ ] **Step 2: Update hook-adapter.md**

After the Tier 2 Stop section, add:

```markdown
### Tier 3 — `runlens watch` (optional foreground autorender)

`runlens watch` polls `.agent-artifacts/artifact_spec.yaml` and
`run_state.json` and debounce-renders `working/report.html`. It never
auto-finalizes. Useful when Stop hooks are unreliable (Cursor CLI, ambiguous
OpenCode per-turn Stop). See
`docs/superpowers/specs/2026-06-06-html-delivery-trigger-strategy-design.md`.
```

- [ ] **Step 3: Mark Tier 3 implemented in design spec**

In `docs/superpowers/specs/2026-06-06-html-delivery-trigger-strategy-design.md`:

- Change header status line to: `Approved; Tier 3 implemented via runlens watch`
- Under Tier 3, replace "Phase 2, not in this change" with implemented note pointing at `autorender.py` + `watch` CLI
- Move SessionStart background spawn to **Future** subsection

- [ ] **Step 4: Add `watch` to AGENTS.md and CLAUDE.md command lists**

In AGENTS.md Acceptance Criteria Workflow block, after `runlens render` line add:

```bash
runlens watch   # optional: debounce-render on spec/state changes (separate terminal)
```

Same one-line addition in CLAUDE.md canonical workflow block.

- [ ] **Step 5: Verify docs parse and tests still pass**

Run:

```bash
uv run pytest -q
uv run runlens watch --help
git diff --check
```

Expected: all pass; help shows `--debounce` and `--poll-interval`.

- [ ] **Step 6: Commit**

```bash
git add examples/adapters/opencode/runlens-artifact-protocol/SKILL.md \
  docs/hook-adapter.md \
  docs/superpowers/specs/2026-06-06-html-delivery-trigger-strategy-design.md \
  AGENTS.md CLAUDE.md
git commit -m "docs: document runlens watch as Tier 3 autorender"
```

---

## Spec coverage self-review

| Spec requirement | Task |
|------------------|------|
| Watch `artifact_spec.yaml` + `run_state.json` | Task 3 `artifact_watch_paths` |
| Debounce ~2s (configurable) | Task 1 controller + Task 4 CLI `--debounce` |
| `render_working_report` only | Task 2 `emit_working_report_on_change` |
| Never auto-finalize | Task 2 `test_emit_never_writes_final_html_even_when_gate_passes` |
| `runlens watch` foreground CLI | Task 4 |
| Best-effort / never raise into agent | Task 2 try/except in emit |
| Debounce coalesces rapid writes | Task 1 `test_debounce_coalesces_rapid_changes` |
| Unrelated file changes ignored | Implicit — only two paths polled |
| Skill + hook docs updated | Task 5 |
| No PostToolUse trigger | Non-goal (documented) |
| SessionStart background | Deferred to Future in Task 5 spec update |

## Execution handoff

Plan saved to `docs/superpowers/plans/2026-06-06-artifact-watch-autorender.md`.

**Two execution options:**

1. **Subagent-Driven (recommended)** — fresh subagent per task, review between tasks
2. **Inline Execution** — implement task-by-task in this session with checkpoints

Which approach?
