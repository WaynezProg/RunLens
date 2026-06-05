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

Refresh the working report:

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

## Do Not

- Do not create checkpoints from `finalize`.
- Do not write `.agent-artifacts/deliverables/final.html` manually.
- Do not put acceptance criteria in `run_state.json`.
- Do not store large HTML bodies, datasets, or chart data in `artifact_spec.yaml`.
- Do not use `--blocked-reason ""`; empty blocked reasons are CLI usage errors.

## Closeout

Before reporting completion, run:

```bash
uv run pytest -q
uv run runlens --help
git diff --check
git status --short --branch
```
