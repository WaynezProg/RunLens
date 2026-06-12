#!/usr/bin/env bash
# uninstall-agent-hooks.sh — Remove RunLens hook adapter from all agent runtimes.
#
# Usage: bash scripts/uninstall-agent-hooks.sh
#
# This script:
#   1. Removes ~/.local/bin/runlens-hook
#   2. Removes hook entries from agent config files
#   3. Removes OpenCode plugin file
#   4. Does NOT remove hooks.jsonl (event log is preserved)

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${GREEN}[runlens]${NC} $*"; }
warn()  { echo -e "${YELLOW}[runlens] WARN${NC} $*"; }
err()   { echo -e "${RED}[runlens] ERROR${NC} $*" >&2; }

HOOK_BIN="$HOME/.local/bin/runlens-hook"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SKILL_NAME="runlens-artifact-protocol"

# ── Step 1: Remove hook binary ─────────────────────────────────────────────
if [ -f "$HOOK_BIN" ]; then
    rm -f "$HOOK_BIN"
    info "Removed: $HOOK_BIN"
else
    warn "Hook binary not found: $HOOK_BIN"
fi

# ── Step 2: Claude Code ────────────────────────────────────────────────────
unset_claude_hooks() {
    local settings="$HOME/.claude/settings.json"
    [ -f "$settings" ] || return 0

    info "Removing Claude Code runlens hooks..."

    # Remove hooks entries that reference runlens-hook
    local cleaned
    if ! cleaned="$(jq '
        .hooks = (
            .hooks | to_entries | map(
                .value = [.value[] | select(
                    (.hooks // []) | all(
                        (.command // "") | test("runlens-hook") | not
                    )
                )]
            ) | from_entries
        )
    ' "$settings" 2>/dev/null)"; then
        warn "  Could not parse $settings. Manual cleanup needed."
        return 1
    fi

    echo "$cleaned" > "$settings"
    info "  Claude Code hooks cleaned ✓"
}
unset_claude_hooks

# ── Step 3: Codex ──────────────────────────────────────────────────────────
unset_codex_hooks() {
    local codex_hooks="$HOME/.codex/hooks.json"
    [ -f "$codex_hooks" ] || return 0

    info "Removing Codex runlens hooks..."
    rm -f "$codex_hooks"
    info "  Codex hooks file removed ✓"
}
unset_codex_hooks

# ── Step 4: OpenCode ───────────────────────────────────────────────────────
unset_opencode_hooks() {
    local plugin_file="$HOME/.config/opencode/plugins/runlens-hooks.ts"
    [ -f "$plugin_file" ] || return 0

    info "Removing OpenCode runlens plugin..."
    rm -f "$plugin_file"
    info "  OpenCode plugin file removed ✓"

    # Remove from opencode.json "plugin" array
    local opencode_config="$HOME/.config/opencode/opencode.json"
    [ -f "$opencode_config" ] || return 0

    python3 -c "
import json
with open('$opencode_config') as f:
    d = json.load(f)
key = 'plugin' if 'plugin' in d else 'plugins'
if key in d:
    d[key] = [p for p in d[key] if 'runlens-hooks' not in str(p)]
with open('$opencode_config', 'w') as f:
    json.dump(d, f, indent=4)
    f.write('\n')
" 2>/dev/null || {
        warn "  Could not update $opencode_config. Manual cleanup needed."
        return 1
    }
    info "  OpenCode plugin registration removed from opencode.json ✓"
}
unset_opencode_hooks

# ── Step 5: Cursor ─────────────────────────────────────────────────────────
unset_cursor_hooks() {
    local cursor_hooks="$HOME/.cursor/hooks.json"
    local project_cursor_hooks="$REPO_ROOT/.cursor/hooks.json"

    for target in "$cursor_hooks" "$project_cursor_hooks"; do
        [ -f "$target" ] || continue
        info "Cleaning Cursor hooks from $target..."

        local cleaned
        if ! cleaned="$(jq '
            .hooks = (
                .hooks | to_entries | map(
                    .value = [.value[] | select(
                        ((.command // "") + (.run // "")) | test("runlens-hook") | not
                    )]
                ) | from_entries
            )
        ' "$target" 2>/dev/null)"; then
            warn "  Could not parse $target. Manual cleanup needed."
            continue
        fi

        echo "$cleaned" > "$target"
        info "  Cursor hooks cleaned ✓"
    done
}
unset_cursor_hooks

# ── Step 6: Trigger skill ─────────────────────────────────────────────────
unset_trigger_skills() {
    local targets=(
        "$HOME/.claude/skills/$SKILL_NAME"
        "$HOME/.codex/skills/$SKILL_NAME"
        "$HOME/.config/opencode/skills/$SKILL_NAME"
        "$HOME/.cursor/skills/$SKILL_NAME"
    )

    local target
    for target in "${targets[@]}"; do
        if [ -d "$target" ]; then
            rm -rf "$target"
            info "Removed trigger skill: $target"
        fi
    done
}
unset_trigger_skills

# ── Done ────────────────────────────────────────────────────────────────────
echo ""
info "═══════════════════════════════════════════════════════════"
info " RunLens hook adapter uninstalled."
info "═══════════════════════════════════════════════════════════"
info ""
info "  Event log preserved: $HOME/.local/share/runlens/hooks.jsonl"
info ""
warn "  Note: Backup files matching '*.bak-runlens-*' were NOT removed."
warn "  Clean them manually if no longer needed:"
warn "    rm -f ~/.claude/settings.json.bak-runlens-*"
warn "    rm -rf ~/.codex/plugins/runlens-hooks.bak-runlens-*"
info ""
