# RunLens Hook Adapter

Cross-agent lifecycle event collector for RunLens. Captures agent lifecycle events
(Claude Code, Codex, OpenCode, Cursor) and normalizes them into a single
`hooks.jsonl` event log.

## Purpose

RunLens is a filesystem-first artifact protocol. The hook adapter extends this by
recording **agent lifecycle events** — session starts, tool executions, session
stops — into a unified event log. This enables:

- Post-hoc analysis of agent behavior across projects
- Correlation of agent actions with artifact state changes
- Future `runlens ingest` pipeline (event → artifact spec updates)

## Architecture

```
Agent lifecycle event
  → ~/.local/bin/runlens-hook  (shell wrapper)
  → runlens hook --event X --agent Y  (Python CLI)
  → normalize + sanitize
  → append ~/.local/share/runlens/hooks.jsonl
```

The `runlens hook` command lives in `src/runlens/hook.py` and exposes a CLI
subcommand. The shell wrapper at `scripts/runlens-hook` resolves the RunLens
project and dispatches via `uv run`.

## Event Schema

Each line in `hooks.jsonl` is one JSON object:

```json
{
  "ts": "2026-06-05T12:30:00Z",
  "cwd": "/Users/waynetu/projects/my-app",
  "git_repo": "kurisu-github/RunLens",
  "agent": "claude-code",
  "event": "SessionStart",
  "raw": {
    "type": "session_start",
    "sessionId": "abc-123"
  }
}
```

| Field      | Type   | Description                                      |
|------------|--------|--------------------------------------------------|
| `ts`       | string | ISO 8601 UTC timestamp                           |
| `cwd`      | string | Working directory when the event fired            |
| `git_repo` | string/null | `owner/repo` from git remote origin, or null |
| `agent`    | string | Agent runtime name                                |
| `event`    | string | Event name (passed via `--event`)                 |
| `raw`      | object | Sanitized payload (secrets stripped)              |

### Secret Sanitization

The following keys are recursively removed from `raw`:
`authorization`, `api_key`, `apikey`, `secret`, `token`, `password`, `bearer`.

This prevents API keys, bearer tokens, and credentials from leaking into the
event log. The sanitization is case-insensitive and recursive (applies to nested
objects and arrays).

## Supported Agent Runtimes

### Runtime Verification Status

| Agent     | Installer | Direct-Call Verified | Runtime Verified |
|-----------|-----------|----------------------|------------------|
| Claude Code | ✓       | ✓                    | ✓                |
| Codex       | ✓       | ✓                    | ✓                |
| OpenCode    | ✓       | ✓                    | ⏳ pending serve/desktop |
| Cursor      | ✓       | ✓                    | ⏳ pending IDE Agent |

"Direct-call verified" means `runlens-hook --event X --agent Y` writes correct
events to `hooks.jsonl` for all four agents.
"Runtime verified" means the agent's native hook/plugin system actually fires
events during a real session.

### Claude Code ✓ (runtime verified)

| Event         | Trigger                                    | Sync?   |
|---------------|--------------------------------------------|---------|
| `SessionStart`| Session starts, clears context, or compacts| async: false |
| `PostToolUse` | After any tool call (no matcher = all)     | async: true  |
| `Stop`        | Session ends                               | async: true  |

Hooks are merged into `~/.claude/settings.json`. The installer backs up the
existing file and uses deep JSON merge. If top-level key types conflict (e.g.
`hooks` is a string instead of an object), the installer aborts.

### Codex ✓ (runtime verified after /hooks trust)

| Event         | Trigger                     |
|---------------|-----------------------------|
| `SessionStart`| Session starts              |
| `Stop`        | Session ends                |

The installer creates `~/.codex/hooks.json`. Codex detects the hooks at
startup (logs show `hook: SessionStart`) but **will not execute commands until
trusted**.

**Manual step required**: In Codex interactive mode, run:

```
/hooks review
/hooks trust
```

For testing only: `codex exec --dangerously-bypass-hook-trust ...`

**Runtime verification**: Verified on 2026-06-05 with Codex CLI 0.134.0 after
interactive `/hooks review` → `/hooks trust`. Starting a new Codex session in
the RunLens repo appended `agent=codex`, `event=SessionStart`, and
`raw.source=startup` to `~/.local/share/runlens/hooks.jsonl`.

**Limitation**: Codex's hook trust is per-session and must be done in
interactive mode. There is no CLI flag to persist trust without the interactive
workflow. Sandbox mode may block hook execution.

### OpenCode ⏳ (installed, pending serve/desktop verification)

| Event            | Trigger          |
|------------------|------------------|
| `session.created`| Session starts   |
| `agent.finished` | Agent completes  |

The installer creates `runlens-hooks.ts` at
`~/.config/opencode/plugins/` **and** registers it in
`~/.config/opencode/opencode.json` → `"plugin"` array.
If the config file doesn't exist, the installer outputs manual instructions.

**Limitation**: Events are limited to what OpenCode's plugin API exposes.

### Cursor ⏳ (installed, pending IDE Agent verification)

| Event  | Trigger                  |
|--------|--------------------------|
| `stop` | Agent session ends       |

Cursor hooks require Cursor ≥ 1.7 (released Oct 2025). The installer checks
for existing `~/.cursor/hooks.json` or `.cursor/hooks.json` in the project root.
If the version field is not `1`, it aborts with a warning.

**Limitation**: IDE hooks are fully supported. CLI hook coverage has historically
diverged from IDE behavior — the `cursor-agent` CLI does not fire `stop` hooks
even when hooks.json is correctly configured. Run a local smoke test to confirm
which events fire in your setup. See the [official Cursor hooks docs](https://docs.cursor.com/context/hooks) for supported events.

## Installation

```bash
bash scripts/install-agent-hooks.sh
```

The installer:
1. Creates `~/.local/share/runlens/` data directory
2. Installs `scripts/runlens-hook` → `~/.local/bin/runlens-hook`
3. Configures Claude Code hooks (merges into `~/.claude/settings.json`)
4. Creates Codex hooks (requires manual `/hooks trust` in Codex)
5. Creates OpenCode plugin at `~/.config/opencode/plugins/` (auto-loaded)
6. Configures Cursor hooks (if Cursor ≥ 1.7 is detected)

**Safety guarantees**:
- Never overwrites a non-RunLens file at `~/.local/bin/runlens-hook`
- Backs up every config before merge (`*.bak-runlens-TIMESTAMP`)
- Aborts if JSON merge would create type conflicts
- Does not use `sudo`, `curl | sh`, `npm install -g`, or `--dangerously-skip-permissions`

## Testing

```bash
# 1. Install
bash scripts/install-agent-hooks.sh

# 2. Fire a test event
echo '{"test": true, "Authorization": "Bearer secret"}' | \
  ~/.local/bin/runlens-hook --event Test --agent claude-code

# 3. Verify event was logged (Authorization should be stripped)
tail -1 ~/.local/share/runlens/hooks.jsonl | python3 -m json.tool

# 4. Start an agent and watch events
tail -f ~/.local/share/runlens/hooks.jsonl

# 5. Run test suite
uv run pytest tests/test_hook.py -v
```

## Uninstallation

```bash
bash scripts/uninstall-agent-hooks.sh
```

This removes:
- `~/.local/bin/runlens-hook`
- Hook entries from `~/.claude/settings.json`
- Codex plugin directory
- OpenCode plugin file (`runlens-hooks.ts`)
- Cursor hook entries

**Preserved**:
- `~/.local/share/runlens/hooks.jsonl` (event log)
- Backup files (`*.bak-runlens-*`) — remove manually if no longer needed

## Development

The hook command is in `src/runlens/hook.py`. The public function is
`normalize_and_append()`:

```python
from runlens.hook import normalize_and_append

result = normalize_and_append(
    event="SessionStart",
    agent="claude-code",
    stdin_data='{"tool": "Bash"}',
    data_home="/tmp/test-data",  # optional, for testing
)
```

Tests are in `tests/test_hook.py`. Run with:

```bash
uv run pytest tests/test_hook.py -v
```
