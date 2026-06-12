# Changelog

## v0.6.0 - 2026-06-12

- Added a Superpowers-style `runlens-artifact-protocol` skill with explicit
  trigger rules for long-running implementation, release, review/debug,
  deployment, and artifact/report work.
- Updated `scripts/install-agent-hooks.sh` to install the trigger skill for
  Claude Code, Codex, OpenCode, and Cursor alongside the lifecycle hooks.
- Added `docs/agent-trigger-map.md` and README install guidance that separates
  skill-trigger responsibilities from Stop-hook and `runlens watch` automation.
