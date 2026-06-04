# RunLens

RunLens is a filesystem-first artifact protocol and CLI for coding agents.

The MVP manages `.agent-artifacts/`, renders static HTML reports, and only writes
`.agent-artifacts/deliverables/final.html` after required acceptance criteria in
`artifact_spec.yaml` pass with evidence.

## MVP Commands

~~~bash
runlens init
runlens update --state working --note "Implemented parser"
runlens render
runlens checkpoint --reason "Useful progress before tests"
runlens finalize
runlens finalize --blocked-reason "Missing access token"
~~~

## Runtime Artifacts

Project-local `.agent-artifacts/` directories are runtime state and are ignored by git.
The dogfood closeout example is committed under `examples/self-run/.agent-artifacts/`.

## Agent Adapters

RunLens keeps the core protocol in the CLI and exposes thin adapter examples for
agent-specific instruction systems:

- `AGENTS.md`: project rules for Codex, Cursor, opencode, Qwen Code, and similar agents.
- `CLAUDE.md`: Claude Code adapter that points back to the same protocol rules.
- `examples/adapters/opencode/runlens-artifact-protocol/SKILL.md`: opencode skill adapter example.
