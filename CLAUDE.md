# RunLens Claude Code Adapter

Claude Code should follow the repository rules in `AGENTS.md`. This file is a
thin adapter for RunLens-specific artifact handling.

## Required Workflow

- Keep root `.agent-artifacts/` as local runtime state. It is ignored by git.
- Use `runlens init` when `.agent-artifacts/` is missing.
- Use `runlens update --state working --note "<milestone>"` after meaningful progress.
- Use `runlens render` to refresh `.agent-artifacts/working/report.html`.
- Use `runlens checkpoint --reason "<reason>"` only when an explicit checkpoint is needed.
- Use `runlens finalize` only after every required criterion in
  `.agent-artifacts/artifact_spec.yaml` is `passed` and has evidence.
- Use `runlens finalize --blocked-reason "<reason>"` only for missing data,
  permission, schema, or user decision.

## Contract Rules

- `artifact_spec.yaml` is the task contract and evidence ledger.
- `run_state.json` is the current execution snapshot only.
- Do not duplicate acceptance criteria into `run_state.json`.
- Do not treat `working/report.html` or checkpoint HTML as final output.
- Do not write `.agent-artifacts/deliverables/final.html` except through
  successful `runlens finalize`.
- Do not expand chart inference or dashboard behavior for the MVP.

## Verification

Run these checks before claiming the repository is ready:

```bash
uv run pytest -q
uv run runlens --help
git diff --check
git status --short --branch
```
