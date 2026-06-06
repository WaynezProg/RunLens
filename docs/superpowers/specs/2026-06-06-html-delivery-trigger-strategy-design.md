# HTML Delivery Trigger Strategy — Design

- **Date:** 2026-06-06
- **Status:** Approved; Tier 3 implemented via `runlens watch` (`autorender.py`)
- **Supersedes in part:** `2026-06-06-proactive-html-on-stop-design.md` — Stop remains
  implemented but is no longer the **primary** delivery contract.
- **Scope:** Agent-facing protocol (`runlens-artifact-protocol` skill), hook adapter
  documentation, future optional `autorender` (Phase 2).

## Problem

RunLens added Stop-hook auto-render so agents would not forget `runlens render`.
In practice, **Stop is not a stable or uniform lifecycle signal** across agent
runtimes:

| Agent       | What `Stop` actually means                          | Reliability        |
|-------------|-----------------------------------------------------|--------------------|
| Claude Code | Whole session ends                                  | Reliable (verified)|
| Codex       | Whole session ends                                  | Requires one-time `/hooks trust` in TUI |
| OpenCode    | `experimental.text.complete` — **one assistant turn**, not session end | Fires often; wrong semantics for "session" |
| Cursor IDE  | Agent session ends                                  | IDE only           |
| Cursor CLI  | N/A                                                 | `stop` does not fire (upstream) |

Teaching agents that "you do not need `render` — Stop does it" sets false
expectations. Humans still see stale or missing HTML when hooks do not fire or
when Stop means something other than "I'm done."

## Decision

**Three-tier trigger model.** Explicit CLI is canonical; Stop is best-effort;
artifact-change watch is the planned automation upgrade.

```
Tier 1 (canonical)  Agent runs `runlens render` / `finalize` at milestones
Tier 2 (bonus)      Stop hook → emit_report_on_stop (already implemented)
Tier 3 (planned)    Debounced render when spec/state files change (Phase 2)
```

Nothing in Tier 2 or Tier 3 replaces Tier 1 for agents that can invoke the CLI.

## Tier 1 — Explicit CLI (canonical)

Agents **must** call `runlens render` after meaningful artifact updates:

- After `criteria pass` / `criteria fail` / `criteria reset`
- After `update --note` when the note is user-visible progress
- Before `finalize` (smoke fixture already does this)

`runlens finalize` remains the only command that **intentionally** writes
`deliverables/final.html` with a gate check. Agents must not assume Stop will
finalize for them.

### Agent closeout checklist

1. `criteria list` — required items `passed` with evidence
2. `runlens render` — working report reflects current spec + state
3. `runlens finalize` — gate pass → `final.html`; else fix criteria and retry

## Tier 2 — Stop hook (best-effort bonus)

`emit_report_on_stop` stays in `src/runlens/autoreport.py` and the `hook`
command's `Stop` branch. Behavior unchanged:

- Skip if no `artifact_spec.yaml`
- Always refresh `working/report.html` when possible
- Finalize only when `required_criteria_passed()` and not already `final`
- Never raise; never call `fail_finalize` on incomplete gate

**Documentation change only:** describe this as a safety net, not the primary
path. Do not tell agents to skip `render`.

### Per-agent honesty (unchanged facts, reframed)

| Agent       | Stop useful for HTML? | Agent should still `render`? |
|-------------|----------------------|------------------------------|
| Claude Code | Often yes            | Yes — do not rely on Stop alone |
| OpenCode    | Per-turn refresh possible | Yes — Stop ≠ session end |
| Codex       | After `/hooks trust` | Yes                          |
| Cursor IDE  | Sometimes            | Yes                          |
| Cursor CLI  | No                   | Yes — only explicit CLI works |

## Tier 3 — Artifact-change autorender (implemented)

**Goal:** automation with a **clear, runtime-agnostic** trigger: when RunLens
protocol files change, debounce and refresh the working report.

**Implementation:** `src/runlens/autorender.py` + `runlens watch` CLI.

### Trigger files

- `.agent-artifacts/artifact_spec.yaml`
- `.agent-artifacts/run_state.json`

### Behavior

- Poll mtime after `runlens init` (`runlens watch` in a separate terminal)
- Debounce ~2s after last write to either file (`--debounce` configurable)
- Call `render_working_report` only — **never** auto-`finalize`
- Same best-effort contract as Stop hook (never raise into agent)

### Future (not implemented)

- Background `watch` spawned from hook `SessionStart` (orphan-process risk; deferred)

### Why not PostToolUse?

PostToolUse fires on every tool call across unrelated edits — high noise, unclear
semantics. Artifact files are the RunLens contract; changes there mean "report
may be stale."

### Non-goals (Phase 2)

- Auto-finalize on artifact change (gate must stay explicit)
- Replacing Tier 1 explicit `render` in the skill
- File watcher for arbitrary repo source files

## Skill changes (`runlens-artifact-protocol`)

Replace "Proactive delivery" section:

- **When to render:** explicit milestones (criteria/state updates, pre-finalize)
- **Stop hook:** optional bonus; semantics vary by runtime
- **Remove:** "You do not need to run `render` manually"

Add a short **Render cadence** subsection with the three trigger tiers.

## Hook adapter doc changes (`docs/hook-adapter.md`)

- Reframe "Stop → HTML delivery" as Tier 2 best-effort
- Add pointer to this spec for canonical Tier 1 workflow
- Keep per-agent matrix; emphasize OpenCode per-turn vs session

## Code changes

Tier 3: `autorender.py` + `runlens watch` (see implementation plan
`docs/superpowers/plans/2026-06-06-artifact-watch-autorender.md`).

## Testing (Phase 2)

- Unit: debounce coalesces rapid spec+state writes into one render
- Unit: spec-only change triggers render; unrelated file change does not
- Integration: `watch` in temp project updates `working/report.html` after `criteria pass`

## Success criteria

- Skill and hook docs no longer claim Stop replaces `render`
- Canonical workflow matches `examples/smoke-fixture/run.sh`
- Stop hook implementation retained; finalize gate semantics unchanged
- Phase 2 spec is actionable without re-litigating Stop semantics
