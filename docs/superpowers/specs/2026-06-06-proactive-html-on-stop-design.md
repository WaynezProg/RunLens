# Proactive HTML Delivery on Agent Stop — Design

- **Date:** 2026-06-06
- **Status:** Approved design (pending spec review)
- **Scope:** RunLens hook adapter + `runlens-artifact-protocol` skill

## Problem

RunLens ships a skill (`runlens-artifact-protocol`) that teaches agents to record
progress and produce HTML via `runlens render` / `finalize`. The skill is
**passive**: the agent must remember to invoke it, so a readable HTML deliverable
is rarely produced on its own. A separate hook adapter exists but only **logs**
lifecycle events to `hooks.jsonl` — it never produces HTML. The gap: nothing
automatically produces the readable HTML deliverable at a natural moment.

## Goal

When an agent session ends (`Stop`), if the current repo is using RunLens,
automatically produce an up-to-date, human-readable HTML report — and, when the
task is genuinely complete, the gated final deliverable — without the agent
having to remember to run anything.

**Non-goals:** forcing agents that never engaged the protocol to produce content;
making Codex/Cursor *CLI* fire hooks they structurally do not; dashboards,
servers, or chart inference.

## Key insight: two independent halves

- **Trigger** (when HTML gets produced) — solved by the Stop hook.
- **Content** (whether the HTML is worth reading) — solved *only* by the agent
  using the skill to record criteria / evidence / notes during the session.

The hook can force the trigger but **cannot** force the content. If the agent
never populated `.agent-artifacts/`, a Stop-triggered render yields an empty
shell. So this design covers both halves: (1) wire Stop → HTML, and (2)
strengthen the skill so `.agent-artifacts/` exists and is populated.

## Architecture

### One shared choke point

All four agents' hooks invoke the same `~/.local/bin/runlens-hook` →
`runlens hook --event <E> --agent <A>`. Therefore the Stop → HTML logic lives in
**exactly one place** — the `hook` command's `Stop` branch — and every agent that
delivers a `Stop` event benefits with **no per-agent code**. Cross-agent wiring is
already done; the only missing piece is the report logic in this shared handler.

### Behavior on `Stop`

Operating in the cwd reported by the event (`project_dir = Path.cwd()`):

1. **Always** log the event to `hooks.jsonl` first (unchanged; never skipped).
2. **Best-effort report step (new)** — only if `./.agent-artifacts/artifact_spec.yaml`
   exists:
   - Run `render` → refresh the working HTML report.
   - If `ArtifactSpec.required_criteria_passed()` is true **and** the project is
     not already `final` with an existing `final.html` → run `finalize` → write
     the gated `deliverables/final.html`.
   - Append a synthetic `report` event to `hooks.jsonl` recording what was
     produced (paths), so `tail -f` shows the delivery.
3. If no `.agent-artifacts/` → do nothing beyond step 1.

### Safety invariants (non-negotiable)

- **Gate is checked before calling finalize.** `finalize` is never invoked when
  required criteria do not pass — because finalize-on-fail sets state to `failed`
  and deletes any stale `final.html`, which on every incomplete Stop would be
  destructive.
- **No exception escapes the hook.** The entire report step is wrapped; logging
  always succeeds even if render/finalize raises.
- **Wrapper contract preserved.** The hook process always exits 0 and writes
  nothing to stdout (see `tests/test_hook_wrapper.py`).
- **Single source of truth.** The pre-check calls the same
  `ArtifactSpec.required_criteria_passed()` predicate `finalize` uses — never a
  divergent copy. `gate_summary()` verdict must continue to match it.

### Module placement

A new composition function, `runlens.autoreport.emit_report_on_stop(project_dir)
-> ReportOutcome`, invoked from the `hook` CLI command's Stop branch. It composes
the existing `store`, `renderer`, and `finalize` logic and adds **no duplicated**
rendering or gate logic. Inputs/outputs are pure (project_dir in; an outcome
object + side-effect files out), so it is unit-testable without spawning an agent.

### Skill change (content half)

Update `runlens-artifact-protocol` SKILL.md to:
- Instruct the agent to run `runlens init` at the **start** of deliverable work so
  `.agent-artifacts/` exists.
- Record criteria / notes as work progresses.
- State explicitly that the Stop hook auto-renders, so the agent's job is to keep
  the spec truthful — not to remember to render.

## Per-agent connection status (documented reality, not aspiration)

| Agent       | Stop fires?                          | Support level                |
|-------------|--------------------------------------|------------------------------|
| Claude Code | ✅ reliably (verified live)          | Full                         |
| OpenCode    | ✅ via plugin (verified live)        | Full                         |
| Codex       | ⚠️ only after one-time TUI `/hooks trust` (no shell equivalent) | Best-effort; one-time manual step |
| Cursor      | ⚠️ IDE fires `stop`; `cursor-agent` CLI does not (upstream) | Best-effort; IDE-only        |

The fail-safe wrapper guarantees Codex/Cursor can no longer **crash** even when
their firing is unreliable. We explicitly stop trying to make Codex/Cursor CLI
fire — that is upstream behavior, and chasing it is the documented cause of prior
churn.

## Error handling

- Wrapper: always exit 0, silent stdout (already landed; `tests/test_hook_wrapper.py`).
- Report step: try/except around render + finalize; failure is recorded into the
  synthetic event payload (e.g. `{"report_error": "..."}`) but never raised.
- finalize pre-gate prevents destructive `failed` transitions on incomplete Stops.

## Testing

- **Unit (`emit_report_on_stop`)** in a temp project:
  - no `.agent-artifacts/` → no-op (only the lifecycle event logged);
  - artifacts present, criteria not passed → render only; no `final.html`; state unchanged;
  - criteria passed → render + `final.html` written; state `final`;
  - already `final` → no re-finalize;
  - render/finalize raising → swallowed; lifecycle event still logged.
- **Integration:** `runlens hook --event Stop` in a temp cwd produces the expected
  files + `hooks.jsonl` entries.
- **Regression:** existing `test_hook.py`, `test_finalize.py`,
  `test_install_agent_hooks.py`, `test_hook_wrapper.py` stay green.

## Rollout

1. Fail-safe wrapper — **DONE** (`scripts/runlens-hook`, reinstalled, 90 tests green).
2. Implement `emit_report_on_stop` + wire into `hook` Stop branch (TDD).
3. Update `runlens-artifact-protocol` SKILL.md (content half).
4. Update `docs/hook-adapter.md`: new Stop behavior + honest per-agent matrix.
5. Reinstall; verify live on Claude + OpenCode; leave Codex/Cursor best-effort.
