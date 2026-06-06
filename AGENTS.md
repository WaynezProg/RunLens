# RunLens Agent Guide

## Project

RunLens is a Python CLI for a filesystem-first agent artifact protocol. It manages
`.agent-artifacts/`, renders static HTML reports, and gates final output through
machine-readable acceptance criteria in `artifact_spec.yaml`.

Do not turn this into a dashboard builder, web server, multi-agent orchestrator,
or chart inference system unless the user explicitly changes scope.

## Source Layout

- `src/runlens/models.py`: Pydantic schemas for run state, artifact spec, criteria, and metadata.
- `src/runlens/store.py`: filesystem protocol paths and read/write/state helpers.
- `src/runlens/renderer.py`: Jinja2 static HTML rendering helpers.
- `src/runlens/cli.py`: Typer commands: `init`, `update`, `render`, `watch`, `checkpoint`, `finalize`.
- `src/runlens/templates/report.html.j2`: static report template.
- `tests/`: pytest coverage for protocol, CLI, renderer, checkpoint, finalize gate, and error UX.
- `docs/superpowers/`: approved design and implementation plan history.
- `examples/self-run/.agent-artifacts/`: committed dogfood example only.

## Protocol Rules

- `artifact_spec.yaml` is the task contract and evidence ledger.
- `run_state.json` is only the current state snapshot; do not copy acceptance criteria into it.
- Root `.agent-artifacts/` is runtime state and must stay ignored by git.
- If a committed example is needed, put it under `examples/self-run/.agent-artifacts/`.
- `render` is a repeatable presentation step and must not write `deliverables/final.html`.
- `checkpoint` is explicit only; no other command should create checkpoint files.
- `finalize` is the acceptance gate:
  - all required criteria must be `passed` and have non-empty `evidence`;
  - failed gates set `failed`, remove stale final output, and must not create checkpoints;
  - `--blocked-reason <text>` sets `blocked` and must not create final output;
  - empty `--blocked-reason ""` is CLI misuse and must not mutate state.

## Acceptance Criteria Workflow

The canonical end-to-end sequence lives in `examples/smoke-fixture/run.sh` and is
enforced by `tests/test_smoke_adapter.py`:

```bash
runlens init
runlens criteria add --id <id> --description "<what>" [--required]
runlens criteria pass --id <id> --evidence "<proof>"
runlens update --state working --note "<milestone>"
runlens render
runlens watch   # optional: debounce-render on spec/state changes (separate terminal)
runlens finalize
```

`init` seeds one required placeholder criterion, `define-criteria`, in `pending`.
There is no `criteria remove`, and `finalize` requires every required criterion to
be `passed` with evidence — so satisfy it via `runlens criteria pass --id
define-criteria --evidence "..."` (or `criteria fail` / `criteria reset` as the task
dictates). Use `runlens criteria list` to inspect status.

## Development

Use `uv`; do not install global Python tooling.

Core checks:

```bash
uv run pytest -q
uv run runlens --help
git diff --check
```

When changing behavior, write or update tests first and watch them fail before implementing.

## HTML And Safety

- Keep report HTML static and readable.
- Jinja output must remain autoescaped.
- Gate summary is a read-only presentation of `required_criteria_passed()` for
  report readability; do not make it a second finalize gate.
- Charts are Vega-Lite `.vl.json` specs referenced by path. The renderer pre-renders
  them to inline SVG via vl-convert, with a data-table/link fallback when a spec is
  missing or invalid. Do not infer chart types or synthesize charts from raw data.
- Keep artifacts metadata-only: path, type, title, status. Do not store large HTML bodies or datasets in YAML.

## CodeGraph

- This repository is CodeGraph-initialized.
- Use CodeGraph tools for structural questions such as symbol lookup, callers, callees, impact, and project file structure.
- Use `rg` for literal strings, config values, logs, and generated artifact text.
- Commit `.codegraph/.gitignore` and agent-facing rules only; do not commit `.codegraph` database files.

## Git Hygiene

- Do not use `git add .`.
- Stage only the files that belong to the current change.
- Preserve user changes and ignored runtime artifacts.
- Before saying work is complete, run the core checks above and confirm `git status --short --branch`.
