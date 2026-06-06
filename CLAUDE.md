# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

`AGENTS.md` is the source of truth for the protocol rules; this file is the
Claude Code adapter and adds the command + architecture orientation.

## Commands

This is a `uv`-managed Python 3.13 project. Do not install global Python tooling.

```bash
uv run pytest -q                              # full test suite
uv run pytest tests/test_finalize.py -q       # one file
uv run pytest tests/test_finalize.py::test_finalize_blocked_does_not_create_final_html  # one test
uv run runlens --help                         # exercise the CLI entrypoint
git diff --check                              # whitespace lint (no ruff/mypy/black configured)
git status --short --branch
```

When changing behavior, write or update the test first and watch it fail before implementing (the repo is TDD-driven; see `AGENTS.md`).

Canonical workflow (single source of truth: `examples/smoke-fixture/run.sh`, enforced by `tests/test_smoke_adapter.py`):

```bash
runlens init
runlens criteria add --id <id> --description "<what>" [--required]
runlens criteria pass --id <id> --evidence "<proof>"   # criteria fail/reset/list also exist
runlens update --state working --note "<milestone>"
runlens render
runlens watch   # optional: debounce-render on spec/state changes (separate terminal)
runlens finalize
```

## Architecture

RunLens is a Typer CLI implementing a filesystem-first artifact protocol for coding
agents. It owns a per-project `.agent-artifacts/` tree and gates final HTML output
behind machine-checkable acceptance criteria. It is deliberately **not** a dashboard,
web server, orchestrator, or chart-inference engine — keep that scope.

Layers (each module has one job; the CLI is the only place they compose):

- `models.py` — Pydantic schemas (`extra="forbid"`, `use_enum_values=True`). The
  `RunStatus` enum (`working → checkpoint/blocked/failed/final`) is the state machine.
  `ArtifactSpec.required_criteria_passed()` is the single source of the finalize gate:
  every `required` criterion must be `passed` **and** carry non-empty `evidence`.
  `ArtifactSpec.gate_summary()` is the read-only presentation of that same gate for the
  report (PASS/FAIL verdict + unmet-required list); its verdict must never diverge from
  `required_criteria_passed()`.
- `store.py` — filesystem protocol: path constants, dir scaffolding, and read/write of
  the two state files. `build_updated_state()` appends the prior snapshot to `history`
  on every transition. Writing state also re-renders `RUN_STATE.md`.
- `criteria.py` — pure spec transforms for the `criteria` subcommands (add/pass/fail/reset),
  raising `CriteriaCommandError` subclasses for expected, traceback-free CLI errors.
- `renderer.py` — Jinja2 (`autoescape=True`, `PackageLoader`) static HTML from spec+state.
  Working/checkpoint/final reports share one `report.html.j2`, differing only by banner
  and output path.
- `charts.py` — turns each `charts[]` entry (a Vega-Lite `.vl.json` referenced by path)
  into a `RenderedChart`: inline SVG via vl-convert when the spec converts, else a
  data-table/link fallback. Validation is delegated to vl-convert (convert succeeds = valid);
  it never raises into render/finalize, and the finalize gate ignores charts entirely.
- `autorender.py` — debounced working-report refresh when artifact spec/state change (`watch`).
- `cli.py` — Typer wiring. `_run_initialized_command` / `_run_criteria_command` centralize
  error UX: missing `.agent-artifacts` → "run init"; bad JSON/YAML/schema → one-line message;
  all exit non-zero without tracebacks.

### Two-file contract (do not blur these)

- `artifact_spec.yaml` — the **task contract and evidence ledger**. Acceptance criteria
  live here and nowhere else.
- `run_state.json` — the **current execution snapshot only** (state, note, last_report,
  history). Never copy acceptance criteria into it.

### Command semantics (the invariants tests enforce)

- `init` is idempotent — never clobbers an existing spec/state. It seeds one required
  placeholder criterion, `define-criteria` (`pending`); there is no `criteria remove`, so
  the finalize gate is only satisfiable by `criteria pass`-ing it (or `fail`/`reset`).
- `render` is a repeatable presentation step; it must not write `deliverables/final.html`.
- `checkpoint` is the *only* command that writes `checkpoints/`; nothing else creates them.
- `finalize` is the acceptance gate:
  - success requires `required_criteria_passed()`; only then is `deliverables/final.html` written.
  - failure (criteria not met / missing / invalid spec) sets `failed`, removes any stale
    `final.html`, and must not create a checkpoint.
  - `--blocked-reason "<text>"` sets `blocked` and must not create final output; empty
    `--blocked-reason ""` is CLI misuse and must not mutate state.

## Runtime artifacts & git hygiene

- Root `.agent-artifacts/` is local runtime state and is git-ignored — leave it that way.
  The only committed example lives under `examples/self-run/.agent-artifacts/`.
- Do not `git add .`; stage only files belonging to the current change, and preserve
  unrelated user edits in a dirty worktree.

## CodeGraph

This repo is CodeGraph-initialized. Prefer `codegraph_*` for structural questions
(symbol lookup, callers/callees, impact, file layout); use `rg` for literal strings,
config values, log lines, and generated artifact text. Do not commit `.codegraph/` db files.
