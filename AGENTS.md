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
- `src/runlens/cli.py`: Typer commands: `init`, `update`, `render`, `checkpoint`, `finalize`.
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
- Chart support is metadata passthrough / table fallback only; do not infer chart types in the MVP.
- Keep artifacts metadata-only: path, type, title, status. Do not store large HTML bodies or datasets in YAML.

## Git Hygiene

- Do not use `git add .`.
- Stage only the files that belong to the current change.
- Preserve user changes and ignored runtime artifacts.
- Before saying work is complete, run the core checks above and confirm `git status --short --branch`.
