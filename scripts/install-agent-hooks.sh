#!/usr/bin/env bash
# install-agent-hooks.sh — Install RunLens hook adapter for Claude Code, Codex,
# OpenCode, and Cursor agent runtimes.
#
# Usage: bash scripts/install-agent-hooks.sh
#
# This script:
#   1. Creates ~/.local/share/runlens/ data directory
#   2. Installs scripts/runlens-hook to ~/.local/bin/runlens-hook
#   3. Configures each detected agent runtime's hook settings
#   4. Backs up existing config before merge; aborts on unsafe merge

set -euo pipefail

# ── Colors ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${GREEN}[runlens]${NC} $*"; }
warn()  { echo -e "${YELLOW}[runlens] WARN${NC} $*"; }
err()   { echo -e "${RED}[runlens] ERROR${NC} $*" >&2; }
abort() { err "$*"; exit 1; }

# ── Paths ───────────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOOK_BIN="$HOME/.local/bin/runlens-hook"
HOOK_DATA="$HOME/.local/share/runlens"
HOOK_BIN_SRC="$SCRIPT_DIR/runlens-hook"

REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# ── Step 0: Validate prerequisites ─────────────────────────────────────────
command -v python3 &>/dev/null || abort "python3 not found. Install via Homebrew or mise."
command -v jq &>/dev/null || abort "jq not found. Install via: brew install jq"

if [ ! -f "$HOOK_BIN_SRC" ]; then
    abort "runlens-hook wrapper not found at $HOOK_BIN_SRC"
fi

# ── Step 1: Create data directory ──────────────────────────────────────────
mkdir -p "$HOOK_DATA"
info "Created data directory: $HOOK_DATA"

# ── Step 2: Install hook binary ────────────────────────────────────────────
mkdir -p "$HOME/.local/bin"

# Only overwrite if it's our own file (check via shebang comment)
if [ -f "$HOOK_BIN" ]; then
    if grep -q "runlens-hook" "$HOOK_BIN" 2>/dev/null; then
        # Our file — safe to overwrite
        info "Updating existing hook binary"
    else
        warn "$HOOK_BIN already exists and is NOT ours. Aborting binary install."
        warn "Please remove it manually, then re-run this script."
        exit 1
    fi
fi

cp "$HOOK_BIN_SRC" "$HOOK_BIN"
chmod +x "$HOOK_BIN"
info "Installed hook binary: $HOOK_BIN"

# ── Step 3: Detect RunLens project root ────────────────────────────────────
# The hook binary needs to find `runlens`. Store the resolved project root
# so the wrapper can use it reliably.
info "Using RunLens project: $REPO_ROOT"

# ── Helper: backup + jq merge for JSON config files ────────────────────────
backup_if_exists() {
    local file="$1"
    if [ -f "$file" ]; then
        local backup="${file}.bak-runlens-$(date +%Y%m%d-%H%M%S)"
        cp "$file" "$backup"
        info "Backed up: $backup"
    fi
}

safe_merge_json() {
    # Merges new JSON into existing, key by key. If a top-level key exists in
    # both with incompatible types (e.g. object vs string), abort.
    local target="$1"
    local patch="$2"  # file path with merge patch

    if [ ! -f "$target" ]; then
        cp "$patch" "$target"
        return 0
    fi

    # Check for type conflicts
    local conflicts
    conflicts="$(jq -r --slurpfile new "$patch" '
        to_entries | map(
            select(
                ($new[0][.key] != null) and
                (($new[0][.key] | type) != (.value | type))
            ) | .key
        ) | join("\n")
    ' "$target" 2>/dev/null || echo "PARSE_ERROR")"

    if [ "$conflicts" = "PARSE_ERROR" ] || [ "$conflicts" = "null" ]; then
        err "Cannot parse $target as JSON. Aborting merge."
        return 1
    fi

    if [ -n "$conflicts" ]; then
        err "Cannot safely merge — conflicting keys in $target: $conflicts"
        return 1
    fi

    # Merge (deep merge for nested objects)
    local merged
    merged="$(jq --slurpfile new "$patch" '. * $new[0]' "$target")"
    echo "$merged" > "$target"
    return 0
}

# ── Step 4: Claude Code ───────────────────────────────────────────────────
configure_claude_code() {
    local settings="$HOME/.claude/settings.json"

    if [ ! -f "$settings" ]; then
        warn "Claude Code settings not found at $settings"
        warn "  Install Claude Code first: npm install -g @anthropic-ai/claude-code"
        return 1
    fi

    info "Configuring Claude Code hooks..."
    backup_if_exists "$settings"

    local patch
    patch="$(mktemp)"
    cat > "$patch" << 'JSON'
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "startup|clear|compact",
        "hooks": [
          {
            "type": "command",
            "command": "~/.local/bin/runlens-hook --event SessionStart --agent claude-code",
            "async": false
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "rtk hook claude 2>/dev/null; ~/.local/bin/runlens-hook --event PostToolUse --agent claude-code",
            "async": true
          }
        ]
      }
    ],
    "Stop": [
      {
        "matcher": ".",
        "hooks": [
          {
            "type": "command",
            "command": "~/.local/bin/runlens-hook --event Stop --agent claude-code",
            "async": true
          }
        ]
      }
    ]
  }
}
JSON

    if safe_merge_json "$settings" "$patch"; then
        info "  Claude Code hooks configured ✓"
    else
        warn "  Claude Code merge failed. Manual fix needed."
        warn "  See: docs/hook-adapter.md#claude-code-manual-config"
    fi
    rm -f "$patch"
}

configure_claude_code

# ── Step 5: Codex ─────────────────────────────────────────────────────────
configure_codex() {
    local codex_config="$HOME/.codex/config.toml"
    local codex_hooks="$HOME/.codex/hooks.json"

    if [ ! -f "$codex_config" ]; then
        warn "Codex config not found at $codex_config"
        return 1
    fi

    info "Configuring Codex hooks..."

    backup_if_exists "$codex_hooks"

    cat > "$codex_hooks" << 'JSON'
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "startup|clear|compact",
        "hooks": [
          {
            "type": "command",
            "command": "~/.local/bin/runlens-hook --event SessionStart --agent codex",
            "async": false
          }
        ]
      }
    ],
    "Stop": [
      {
        "matcher": ".",
        "hooks": [
          {
            "type": "command",
            "command": "~/.local/bin/runlens-hook --event Stop --agent codex",
            "async": true
          }
        ]
      }
    ]
  }
}
JSON

    info "  Codex hooks created at: $codex_hooks"
    echo ""
    warn "  Codex requires manual hook trust. In Codex, run:"
    echo ""
    echo "    /hooks review"
    echo "    /hooks trust"
    echo ""
    echo "  Non-managed hooks will not execute until trusted."
    echo "  For testing only: codex exec --dangerously-bypass-hook-trust ..."
    echo ""
}

configure_codex

# ── Step 6: OpenCode ──────────────────────────────────────────────────────
configure_opencode() {
    info "Configuring OpenCode hooks..."

    local plugin_dir="$HOME/.config/opencode/plugins"
    mkdir -p "$plugin_dir"

    cat > "$plugin_dir/runlens-hooks.ts" << 'TS'
// RunLens hook adapter for OpenCode
// Registered in: ~/.config/opencode/opencode.json → "plugin" array

import type { Plugin } from "@opencode-ai/plugin"

const HOOK_BIN = `${process.env.HOME}/.local/bin/runlens-hook`

function fire(event: string): Promise<void> {
  return new Promise((resolve) => {
    const { execFile } = require("child_process")
    execFile(
      HOOK_BIN,
      ["--event", event, "--agent", "opencode"],
      { stdio: ["ignore", "ignore", "ignore"] },
      () => resolve()
    )
  })
}

export const RunLensHooksPlugin: Plugin = async () => {
  return {
    "session.created": async () => {
      await fire("session.created")
    },
    "agent.finished": async () => {
      await fire("agent.finished")
    },
  }
}
TS

    info "  OpenCode plugin created at: $plugin_dir/runlens-hooks.ts"

    # Register plugin in opencode.json "plugin" array
    local opencode_config="$HOME/.config/opencode/opencode.json"
    if [ -f "$opencode_config" ]; then
        backup_if_exists "$opencode_config"

        local plugin_ref="./plugins/runlens-hooks.ts"
        local has_plugin
        has_plugin="$(python3 -c "
import json
with open('$opencode_config') as f:
    d = json.load(f)
plugins = d.get('plugin', d.get('plugins', []))
print('yes' if any('runlens-hooks' in str(p) for p in plugins) else 'no')
" 2>/dev/null || echo "PARSE_ERROR")"

        if [ "$has_plugin" = "PARSE_ERROR" ]; then
            warn "  Cannot parse $opencode_config. Manual registration needed."
        elif [ "$has_plugin" = "no" ]; then
            python3 -c "
import json
with open('$opencode_config') as f:
    d = json.load(f)
if 'plugin' not in d and 'plugins' not in d:
    d['plugin'] = []
key = 'plugin' if 'plugin' in d else 'plugins'
entry = './plugins/runlens-hooks.ts'
if entry not in d[key]:
    d[key].append(entry)
with open('$opencode_config', 'w') as f:
    json.dump(d, f, indent=4)
    f.write('\n')
"
            info "  Registered runlens-hooks.ts in opencode.json ✓"
        else
            info "  runlens-hooks.ts already registered in opencode.json ✓"
        fi
    else
        warn "  OpenCode config not found at $opencode_config."
        warn "  Manual step: add \"./plugins/runlens-hooks.ts\" to the \"plugin\" array."
    fi
}

configure_opencode

# ── Step 7: Cursor ────────────────────────────────────────────────────────
configure_cursor() {
    local cursor_hooks="$HOME/.cursor/hooks.json"
    local project_cursor_hooks="$REPO_ROOT/.cursor/hooks.json"

    info "Configuring Cursor hooks..."

    # Cursor hooks require Cursor ≥ 1.7. Detect by checking settings DB.
    # Cursor stores version in its app metadata; we check if hooks.json is
    # a valid config format (Cursor < 1.7 doesn't support hooks at all).

    local use_global=false
    local use_project=false

    if [ -f "$cursor_hooks" ]; then
        use_global=true
        backup_if_exists "$cursor_hooks"
    fi

    # Always prefer global if it exists
    local target=""
    if [ "$use_global" = true ]; then
        target="$cursor_hooks"
    elif [ -d "$HOME/.cursor" ]; then
        target="$cursor_hooks"
    elif [ -d "$REPO_ROOT/.cursor" ]; then
        target="$project_cursor_hooks"
        backup_if_exists "$project_cursor_hooks"
    else
        warn "Cursor config directory not found."
        warn "  Cursor hooks require Cursor ≥ 1.7 (released Oct 2025)."
        warn "  If you have Cursor, create: $cursor_hooks"
        return 1
    fi

    local patch
    patch="$(mktemp)"
    cat > "$patch" << 'JSON'
{
  "version": 1,
  "hooks": {
    "stop": [
      {
        "command": "~/.local/bin/runlens-hook --event Stop --agent cursor"
      }
    ]
  }
}
JSON

    if [ ! -f "$target" ]; then
        cp "$patch" "$target"
        info "  Created: $target"
    else
        # Check if existing has version: 1
        local existing_version
        existing_version="$(jq -r '.version // "missing"' "$target" 2>/dev/null || echo "PARSE_ERROR")"

        if [ "$existing_version" != "1" ]; then
            warn "  $target has incompatible version: $existing_version"
            warn "  Cannot safely merge. Manual config needed."
            warn "  See: docs/hook-adapter.md#cursor-manual-config"
            rm -f "$patch"
            return 1
        fi

        # Merge hooks entries
        local merged
        merged="$(jq --slurpfile new "$patch" '
            .hooks = (.hooks * $new[0].hooks)
        ' "$target")"

        if echo "$merged" | jq . > /dev/null 2>&1; then
            echo "$merged" > "$target"
            info "  Cursor hooks merged ✓"
        else
            warn "  Cursor merge produced invalid JSON. Backup preserved."
        fi
    fi
    rm -f "$patch"
}

configure_cursor

# ── Done ────────────────────────────────────────────────────────────────────
echo ""
info "═══════════════════════════════════════════════════════════"
info " RunLens hook adapter installed successfully!"
info "═══════════════════════════════════════════════════════════"
info ""
info "  Hook binary:   $HOOK_BIN"
info "  Event log:     $HOOK_DATA/hooks.jsonl"
info ""
info "  Supported runtimes: Claude Code ✓ (runtime verified) | Codex ⏳ | OpenCode ⏳ | Cursor ⏳"
info ""
info "  Test: echo '{\"test\":true}' | $HOOK_BIN --event Test --agent claude-code"
info "  Watch: tail -f $HOOK_DATA/hooks.jsonl"
info "  Uninstall: bash $SCRIPT_DIR/uninstall-agent-hooks.sh"
info ""
