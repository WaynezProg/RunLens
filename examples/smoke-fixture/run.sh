#!/usr/bin/env bash
# Canonical RunLens workflow — single source of truth for the v0.3 smoke test.
#
# tests/test_smoke_adapter.py parses the `runlens ...` lines below, runs them in
# an empty temp dir, and asserts the sequence produces deliverables/final.html.
# Every agent adapter (AGENTS.md / CLAUDE.md / opencode SKILL.md) must document
# the same commands.
#
# To run by hand from an empty directory (with runlens installed, e.g. `uv run`):
#   bash run.sh        # or prefix each line with `uv run`
set -euo pipefail

# 1. Scaffold .agent-artifacts/ (idempotent).
runlens init

# 2. `init` ships one required placeholder criterion, `define-criteria`, in
#    `pending`. There is no `criteria remove`, and finalize requires EVERY
#    required criterion to be `passed` with evidence — so it must be satisfied.
runlens criteria pass --id define-criteria --evidence "Smoke fixture: placeholder satisfied by the canonical workflow."

# 3. Add and pass a task-specific criterion (demonstrates `criteria add`/`pass`).
runlens criteria add --id smoke-report --description "Working report renders for the smoke task."
runlens criteria pass --id smoke-report --evidence "runlens render wrote .agent-artifacts/working/report.html"

# 4. Record progress and refresh the working report.
runlens update --state working --note "Smoke fixture progress"
runlens render

# 5. Acceptance gate: writes deliverables/final.html only because all required
#    criteria pass with evidence.
runlens finalize
