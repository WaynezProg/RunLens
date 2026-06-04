# RunLens MVP Design

## Goal

RunLens is a filesystem-first artifact protocol and Python CLI for coding agents.
It lets Codex, Claude Code, opencode, Cursor, and Qwen Code write structured task
state and artifacts so a human can inspect HTML reports instead of reading chat
logs or scattered Markdown files.

The MVP intentionally stops at protocol, CLI, run state, acceptance gating, and
basic HTML rendering. It does not include a web server, dashboard builder,
multi-agent orchestration, or chart inference.

## Project Context

The `RunLens` directory starts empty. The project should be initialized as a new
Python package and a new git repository. The implementation should use `uv` for
project and dependency management, with Typer for the CLI, Pydantic for schema
validation, Jinja2 for HTML rendering, PyYAML for YAML parsing, and pytest for
tests.

## Filesystem Protocol

The CLI manages this directory tree:

```text
.agent-artifacts/
  artifact_spec.yaml
  run_state.json
  RUN_STATE.md

  working/
    report.html
    data/
    charts/

  checkpoints/
    checkpoint-YYYYMMDD-HHMMSS.html

  deliverables/
    final.html
```

`artifact_spec.yaml` is the machine-readable task contract and evidence ledger.
`run_state.json` is the current execution state snapshot. `RUN_STATE.md` is the
human-readable state summary.

## State Machine

Only these states are valid:

- `working`: work is in progress.
- `checkpoint`: a useful intermediate report exists, but the task contract is
  not complete.
- `blocked`: required data, permission, schema, or decision is missing.
- `failed`: execution or validation failed.
- `final`: all required acceptance criteria passed and final output exists.

Having artifacts does not imply `final`. `final` is only valid after the
acceptance gate passes.

## Artifact Spec

`artifact_spec.yaml` owns task contract data and evidence:

```yaml
task:
  title: RunLens task
  description: Filesystem-first artifact protocol run

acceptance_criteria:
  - id: define-criteria
    description: Replace this placeholder with task-specific acceptance criteria.
    status: pending
    evidence: null
    required: true

artifacts: []
charts: []
```

Acceptance criteria fields:

- `id`: stable machine-readable identifier.
- `description`: human-readable requirement.
- `status`: one of `pending`, `passed`, or `failed`.
- `evidence`: file path, command output summary, or note proving the status.
- `required`: boolean gate flag.

`artifacts[]` and `charts[]` may contain only metadata such as `path`, `type`,
`title`, and `status`. They must not store large HTML bodies, large datasets, or
chart data. Chart support in the MVP is passthrough only: if a Vega-Lite spec
path is listed, the HTML renderer can link or embed metadata for it; if it
cannot render a chart, it falls back to a table or link. The MVP does not infer
chart type from intent.

## Run State

`run_state.json` stores the current execution snapshot:

```json
{
  "state": "working",
  "note": "Initialized RunLens artifacts.",
  "last_report": ".agent-artifacts/working/report.html",
  "updated_at": "2026-06-04T00:00:00Z",
  "history": []
}
```

`run_state.json` must not copy acceptance criteria. `artifact_spec.yaml` is the
only source of truth for criteria and evidence.

## CLI Commands

### `runlens init`

Creates `.agent-artifacts/`, the protocol subdirectories, `artifact_spec.yaml`,
`run_state.json`, and `RUN_STATE.md`.

The generated `artifact_spec.yaml` includes the required `define-criteria`
placeholder above. Because that criterion is `pending` with empty evidence,
`finalize` must fail by default after `init`.

### `runlens update --state <state> --note <note>`

Updates only `run_state.json` and `RUN_STATE.md`. It does not modify
`artifact_spec.yaml` or acceptance criteria.

### `runlens render`

Renders the current presentation report to
`.agent-artifacts/working/report.html`.

`render` is a repeatable presentation step. It reads `artifact_spec.yaml` and
`run_state.json`, then writes the working report. It is not an acceptance gate
and must not write `.agent-artifacts/deliverables/final.html`.

### `runlens checkpoint --reason <reason>`

Creates `.agent-artifacts/checkpoints/checkpoint-YYYYMMDD-HHMMSS.html` and sets
state to `checkpoint`. Checkpoints are explicit only; no other command creates
them implicitly.

### `runlens finalize [--blocked-reason <reason>]`

`finalize` is the acceptance gate.

It determines pass/fail only from `artifact_spec.yaml`:

- If every required criterion has `status: passed` and non-empty `evidence`,
  set state to `final`, write `.agent-artifacts/deliverables/final.html`, and
  exit zero.
- If any required criterion is not passed or has empty evidence, set state to
  `failed`, write/update a failed working report, do not create `final.html`,
  and exit non-zero.
- If `--blocked-reason` is provided, set state to `blocked`, write/update a
  blocked working report, do not create `final.html`, and exit non-zero.

`finalize` must not read notes to decide acceptance. It must not automatically
create checkpoints.

## HTML Rendering

The Jinja2 renderer produces readable static HTML with:

- Current state and last note.
- Task title and description.
- Acceptance criteria table with status, required flag, and evidence.
- Artifact and chart metadata tables.
- Clear failed or blocked banner when relevant.

The renderer should be deterministic enough for tests to assert key strings and
output paths. It should remain plain static HTML.

## Validation And Error Handling

Pydantic models validate:

- Allowed run states.
- Allowed criterion statuses.
- Required fields in `artifact_spec.yaml`.
- Metadata-only shape for `artifacts[]` and `charts[]`.

Malformed YAML/JSON or invalid schema should fail with a non-zero CLI exit and
a readable error. Validation failures should not create `final.html`.

## Test Coverage

pytest coverage should include:

- `init` creates the expected directory tree and files.
- `init` writes the required `define-criteria` placeholder with `pending` status
  and empty evidence.
- `update` changes `run_state.json` and `RUN_STATE.md`.
- `update` does not modify acceptance criteria in `artifact_spec.yaml`.
- `render` can be rerun and only writes `working/report.html`.
- `finalize` fails with non-zero exit when required criteria are not all passed
  with evidence.
- `finalize` failure sets state to `failed` and does not create
  `deliverables/final.html`.
- `finalize` failure does not automatically create a checkpoint.
- `finalize --blocked-reason <reason>` sets state to `blocked`, creates a
  blocked working report, and does not create `deliverables/final.html`.
- `finalize` succeeds only when all required criteria are `passed` and have
  non-empty evidence.
- Successful `finalize` writes `deliverables/final.html`.
- Chart metadata passthrough and table/link fallback appear in the HTML report.

## Acceptance Criteria For The MVP

- A human can inspect `.agent-artifacts/working/report.html` and understand
  current progress without reading chat logs.
- The CLI clearly distinguishes `checkpoint`, `blocked`, `failed`, and `final`.
- `finalize` cannot produce `final.html` unless the required criteria in
  `artifact_spec.yaml` pass with evidence.
- The project has pytest coverage for the gate behavior and protocol files.

## Deferred Work

- `init --empty`.
- Chart intent inference.
- Vega-Lite spec generation from chart intent.
- Rich interactive dashboard rendering.
- Web server or browser preview mode.
- Codex Skill, Claude Code hook, Cursor rule, opencode adapter, and Qwen Code
  adapter.
- Multi-agent orchestration.
