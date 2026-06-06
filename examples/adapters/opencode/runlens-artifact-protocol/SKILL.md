---
name: runlens-artifact-protocol
description: Use when an opencode agent works in a repository that uses RunLens for filesystem-first progress reports and acceptance-gated HTML artifacts.
---

# RunLens Artifact Protocol

Use RunLens to keep agent progress inspectable without requiring the human to
read the chat log.

## Scope

- Maintain `.agent-artifacts/` as local runtime state for the current repository.
- Produce static HTML reports with the RunLens CLI.
- Gate final deliverables through acceptance criteria in `artifact_spec.yaml`.
- Do not implement dashboard building, web servers, multi-agent orchestration,
  or chart inference as part of this adapter.

## State Rules

- `working`: task is in progress.
- `checkpoint`: useful intermediate output exists, but the task contract is not complete.
- `blocked`: required data, permission, schema, or decision is missing.
- `failed`: execution or validation failed.
- `final`: all required acceptance criteria passed with evidence.

Final means every required criterion in `.agent-artifacts/artifact_spec.yaml` has:

- `status: passed`
- non-empty `evidence`

Never infer final state from notes, generated files, or a successful render.

## Commands

Initialize runtime files:

```bash
uv run runlens init
```

Define and pass acceptance criteria (the finalize gate reads these):

```bash
uv run runlens criteria add --id parser --description "CSV parser handles quoted fields" --required
uv run runlens criteria pass --id parser --evidence "tests/test_parser.py: 12 passed"
```

`init` seeds a required placeholder criterion, `define-criteria`, in `pending`. There
is no `criteria remove`, and `finalize` needs every required criterion `passed` with
evidence — so pass it too (`uv run runlens criteria pass --id define-criteria
--evidence "..."`). Use `criteria fail` / `criteria reset` / `criteria list` as needed.

Record meaningful progress:

```bash
uv run runlens update --state working --note "Implemented parser"
```

Refresh the working report (required at milestones — see **Render cadence**):

```bash
uv run runlens render
```

Create an explicit checkpoint:

```bash
uv run runlens checkpoint --reason "Useful progress before tests finished"
```

Finalize only when the contract passes:

```bash
uv run runlens finalize
```

Mark blocked only with a real reason:

```bash
uv run runlens finalize --blocked-reason "Missing production API access"
```

## Render cadence (when HTML is produced)

Three tiers — **you own Tier 1**; do not assume hooks will render for you.

### Tier 1 — Explicit CLI (canonical)

Run `uv run runlens render` after:

- `criteria pass` / `criteria fail` / `criteria reset`
- `update --note` when the note is user-visible progress
- Before `finalize` (always)

Run `uv run runlens finalize` only when every required criterion is `passed`
with evidence. Final HTML is never implied by a successful `render`.

### Tier 2 — Stop hook (best-effort bonus)

If lifecycle hooks are installed, a `Stop` event may refresh
`working/report.html` and — when the gate already passes — write
`deliverables/final.html`. **Do not rely on this:**

- OpenCode `Stop` fires per assistant turn, not session end.
- Cursor `cursor-agent` CLI does not fire `stop`.
- Codex needs a one-time `/hooks trust` in the TUI.

Hooks never populate criteria for you. Empty or stale spec → empty shell HTML.

### Tier 3 — Artifact watch (optional automation)

In a separate terminal, run:

```bash
uv run runlens watch
```

This polls `artifact_spec.yaml` and `run_state.json` and debounce-renders
`working/report.html` (~2s after the last change). It **never** writes
`final.html`. Tier 1 explicit `render` / `finalize` still apply at closeout.

## Closeout

Before reporting completion:

```bash
uv run runlens criteria list
uv run runlens render
uv run runlens finalize
uv run pytest -q
uv run runlens --help
git diff --check
git status --short --branch
```

## Do Not

- Do not skip `render` and assume the Stop hook will refresh the report.
- Do not create checkpoints from `finalize`.
- Do not write `.agent-artifacts/deliverables/final.html` manually.
- Do not put acceptance criteria in `run_state.json`.
- Do not store large HTML bodies, datasets, or chart data in `artifact_spec.yaml`.
- Do not use `--blocked-reason ""`; empty blocked reasons are CLI usage errors.
