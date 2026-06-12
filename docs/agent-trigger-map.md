# RunLens Agent Trigger Map

RunLens has two separate mechanisms:

- **Skill trigger** tells the agent when to start using the protocol.
- **Lifecycle hooks** render or finalize existing `.agent-artifacts/` on `Stop`.

Hooks do not create criteria, evidence, or useful content. The skill must trigger
early enough for the agent to run `runlens init`, add criteria, pass/fail them
with evidence, and call `runlens render` at milestones.

## When RunLens Should Trigger

Trigger RunLens when the task is:

- Long-running implementation, review/debug, deployment, or release work.
- Expected to leave an inspectable HTML artifact, final report, timeline, or
  evidence ledger.
- Already inside a repo with `.agent-artifacts/`, or the user mentions RunLens,
  `final.html`, acceptance criteria, artifacts, evidence, or asks the agent to
  keep working until done.

Do not trigger RunLens for a quick answer, simple translation, one read-only
shell command, or a small lookup unless the user explicitly asks for an artifact.

## Platform Entrypoints

| Platform | Skill entrypoint | Hook entrypoint | Notes |
| --- | --- | --- | --- |
| Claude Code | `~/.claude/skills/runlens-artifact-protocol/SKILL.md` | `~/.claude/settings.json` via `~/.local/bin/runlens-hook` | Skill trigger plus `SessionStart`, `PostToolUse`, and `Stop` hooks. |
| Codex | `~/.codex/skills/runlens-artifact-protocol/SKILL.md` | `~/.codex/hooks.json` via `~/.local/bin/runlens-hook` | Requires one-time `/hooks review` and `/hooks trust` for unmanaged hooks. |
| OpenCode | `~/.config/opencode/skills/runlens-artifact-protocol/SKILL.md` | `~/.config/opencode/plugins/runlens-hooks.ts` | `Stop` maps to `experimental.text.complete`, which can fire per assistant turn. |
| Cursor | `~/.cursor/skills/runlens-artifact-protocol/SKILL.md` | `~/.cursor/hooks.json` via `~/.local/bin/runlens-hook` | IDE stop hooks are supported; `cursor-agent` CLI stop coverage is unreliable. |

Install all four skill entrypoints and hook adapters with:

```bash
bash scripts/install-agent-hooks.sh
```

Remove them with:

```bash
bash scripts/uninstall-agent-hooks.sh
```

## Trigger Responsibilities

When the skill triggers, the agent must:

- Run `runlens init` if `.agent-artifacts/` is missing.
- Add task-specific required criteria and pass the placeholder
  `define-criteria` when real criteria exist.
- Keep `artifact_spec.yaml` as the evidence ledger and `run_state.json` as the
  state snapshot.
- Run `runlens render` after visible milestones and before closeout.
- Run `runlens finalize` only after every required criterion is `passed` with
  non-empty evidence.

## Automation Responsibilities

The Stop hook is a best-effort bonus:

- If `.agent-artifacts/artifact_spec.yaml` exists, `Stop hook` refreshes
  `.agent-artifacts/working/report.html`.
- If the same required-criteria gate already passes, it writes
  `.agent-artifacts/deliverables/final.html`.
- If `.agent-artifacts/` is missing, it records lifecycle telemetry only.

`runlens watch` is an optional foreground helper. It debounce-renders the working
report from artifact changes, but it never finalizes.
