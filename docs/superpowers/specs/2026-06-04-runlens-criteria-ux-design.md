# RunLens v0.2.0 Criteria UX Design

## Goal

RunLens v0.2.0 adds a Criteria UX so coding agents can maintain
`.agent-artifacts/artifact_spec.yaml` through CLI commands instead of editing YAML
by hand.

The purpose is to reduce final gate mistakes. Criteria IDs are gate keys, so the
CLI must preserve existing criteria unless the user explicitly changes their
status through a criteria command.

## Project Context

RunLens already has the core model and gate behavior needed for this feature:

- `AcceptanceCriterion` stores `id`, `description`, `status`, `evidence`, and
  `required`.
- `ArtifactSpec.required_criteria_passed()` requires every required criterion to
  be `passed` with non-empty evidence.
- `finalize` reads `artifact_spec.yaml` and writes run state or final output
  based on the existing gate.

The new work is therefore a CLI editing layer for acceptance criteria. It must
not change the artifact protocol, renderer, chart behavior, adapter docs, or
state machine.

## Commands

Add a Typer subgroup under the existing CLI:

```text
runlens criteria list
runlens criteria add --id tests --description "Tests pass" --required
runlens criteria pass --id tests --evidence "uv run pytest -q: 43 passed"
runlens criteria fail --id tests --evidence "pytest failed: ..."
runlens criteria reset --id tests
```

### `runlens criteria list`

Loads `.agent-artifacts/artifact_spec.yaml` and prints the acceptance criteria in
a stable line-oriented format suitable for humans and simple logs:

```text
<id>	<status>	required=<true|false>	evidence=<evidence-or-empty>	<description>
```

It does not mutate any file.

### `runlens criteria add`

Adds a criterion to `artifact_spec.yaml` with:

- `id`: the provided stable gate key.
- `description`: the provided requirement text.
- `status`: `pending`.
- `evidence`: `null`.
- `required`: `true` when `--required` is supplied, otherwise `false`.

If the criterion ID already exists, the command exits non-zero, prints:

```text
Criterion already exists: <id>
```

and must not mutate `artifact_spec.yaml`.

### `runlens criteria pass`

Sets the matching criterion to:

- `status: passed`
- `evidence: <provided evidence>`

The `--evidence` value must be non-empty after trimming whitespace. Empty
evidence is CLI misuse, exits non-zero, and must not mutate `artifact_spec.yaml`.

### `runlens criteria fail`

Sets the matching criterion to:

- `status: failed`
- `evidence: <provided evidence>`

Evidence is recorded so failed gates carry a useful reason in the source of
truth.

### `runlens criteria reset`

Sets the matching criterion to:

- `status: pending`
- `evidence: null`

It preserves `id`, `description`, and `required`.

## Missing Criteria

`pass`, `fail`, and `reset` require an existing criterion ID. If the ID is not
found, the command exits non-zero and must not mutate `artifact_spec.yaml`.

The exact error text should include the missing ID so an agent can repair the
command without inspecting the YAML manually.

Use this error text:

```text
Criterion not found: <id>
```

## Data Boundary

Criteria commands only mutate:

```text
.agent-artifacts/artifact_spec.yaml
```

They must not mutate:

- `.agent-artifacts/run_state.json`
- `.agent-artifacts/RUN_STATE.md`
- `.agent-artifacts/working/report.html`
- `.agent-artifacts/checkpoints/*`
- `.agent-artifacts/deliverables/final.html`

They also must not call renderer helpers, state helpers, or finalize logic.

## Helper Boundary

Implement a small spec helper layer for pure data operations, such as:

- `add_criterion`
- `set_criterion_status`
- `reset_criterion`

These helpers operate on `ArtifactSpec` data and return updated spec data. They
must not touch run state, renderer output, checkpoints, final output, or
`finalize`.

The CLI command layer is responsible for loading `artifact_spec.yaml`, invoking
the helper, writing the updated spec, and converting expected errors into
readable non-zero CLI exits.

A service class is intentionally out of scope. The feature is a narrow edit
surface over one YAML file, not a new application service boundary.

## Finalize Behavior

`finalize` remains unchanged.

It still succeeds only when all required criteria in `artifact_spec.yaml` are
`passed` and have non-empty evidence. It still fails when required criteria are
pending, failed, missing evidence, invalid, or absent.

Criteria commands make it easier to prepare the input to the gate; they do not
change the gate.

## Error Handling

Expected criteria command errors should exit non-zero without tracebacks:

- run not initialized
- invalid artifact data
- duplicate criterion ID on `add`
- missing criterion ID on `pass`, `fail`, or `reset`
- empty evidence on `pass`

Duplicate add has a fixed error string:

```text
Criterion already exists: <id>
```

Missing criteria have a fixed error string:

```text
Criterion not found: <id>
```

Empty pass evidence has a fixed error string:

```text
Evidence cannot be empty.
```

## Test Coverage

Add pytest coverage for:

- `criteria add` creates a criterion with required status set from the flag,
  `status: pending`, and `evidence: null`.
- `criteria add` with an existing ID exits non-zero, prints
  `Criterion already exists: <id>`, and does not mutate `artifact_spec.yaml`.
- `criteria pass` requires non-empty evidence and does not mutate on empty
  evidence.
- `criteria pass` sets `status: passed` and records evidence.
- `criteria fail` sets `status: failed` and records evidence.
- `criteria reset` returns a criterion to `pending` and clears evidence.
- `criteria pass`, `criteria fail`, and `criteria reset` exit non-zero for a
  missing criterion ID.
- every criteria command leaves `run_state.json` and `RUN_STATE.md` unchanged.
- `finalize` still succeeds only when required criteria are passed with
  non-empty evidence.

## Acceptance Criteria

- Agents can update acceptance criteria through `runlens criteria` without
  manually editing YAML.
- Criteria commands mutate only `artifact_spec.yaml`.
- Duplicate criterion IDs cannot overwrite existing status or evidence.
- `pass` cannot create a false passing gate without evidence.
- Existing finalize gate semantics are preserved.
