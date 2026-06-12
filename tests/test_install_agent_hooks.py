import json
import os
import subprocess
from pathlib import Path


def test_installer_keeps_codex_hook_definition_stable(tmp_path: Path):
    repo = Path(__file__).resolve().parents[1]
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    (home / ".claude" / "settings.json").write_text("{}\n", encoding="utf-8")
    (home / ".codex").mkdir(parents=True)
    (home / ".codex" / "config.toml").write_text("[hooks.state]\n", encoding="utf-8")
    (home / ".config" / "opencode").mkdir(parents=True)
    (home / ".config" / "opencode" / "opencode.json").write_text(
        '{"plugin":[]}\n',
        encoding="utf-8",
    )
    (home / ".cursor").mkdir(parents=True)

    env = os.environ.copy()
    env["HOME"] = str(home)

    command = ["bash", "scripts/install-agent-hooks.sh"]
    first = subprocess.run(command, cwd=repo, env=env, text=True, capture_output=True)
    assert first.returncode == 0, first.stderr + first.stdout

    codex_hooks = home / ".codex" / "hooks.json"
    first_content = codex_hooks.read_text(encoding="utf-8")
    first_config = json.loads(first_content)
    stop_hook = first_config["hooks"]["Stop"][0]["hooks"][0]
    assert stop_hook["async"] is False

    second = subprocess.run(command, cwd=repo, env=env, text=True, capture_output=True)
    assert second.returncode == 0, second.stderr + second.stdout

    assert codex_hooks.read_text(encoding="utf-8") == first_content
    assert not list((home / ".codex").glob("hooks.json.bak-runlens-*"))


def test_installer_claude_hooks_are_cursor_compatible(tmp_path: Path):
    """Cursor reads ~/.claude/settings.json for Claude-compat and calls
    `matcher.split(...)` on every hook block, so each block MUST have a string
    `matcher`; it also has no `async` field. The installer must emit a `matcher`
    on every Claude hook block and never write `async`."""
    repo = Path(__file__).resolve().parents[1]
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    (home / ".claude" / "settings.json").write_text("{}\n", encoding="utf-8")
    (home / ".codex").mkdir(parents=True)
    (home / ".codex" / "config.toml").write_text("[hooks.state]\n", encoding="utf-8")
    (home / ".config" / "opencode").mkdir(parents=True)
    (home / ".config" / "opencode" / "opencode.json").write_text(
        '{"plugin":[]}\n', encoding="utf-8"
    )
    (home / ".cursor").mkdir(parents=True)

    env = os.environ.copy()
    env["HOME"] = str(home)

    result = subprocess.run(
        ["bash", "scripts/install-agent-hooks.sh"],
        cwd=repo,
        env=env,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr + result.stdout

    settings = json.loads((home / ".claude" / "settings.json").read_text(encoding="utf-8"))
    hooks = settings["hooks"]
    async_entries = [
        entry
        for blocks in hooks.values()
        for block in blocks
        for entry in block.get("hooks", [])
        if "async" in entry
    ]
    assert async_entries == [], f"Claude hooks must not contain `async`: {async_entries}"

    # Every hook block must carry a string `matcher` (Cursor calls .split() on it).
    blocks_without_matcher = [
        (event, block)
        for event, blocks in hooks.items()
        for block in blocks
        if not isinstance(block.get("matcher"), str)
    ]
    assert blocks_without_matcher == [], (
        f"every Claude hook block needs a string matcher: {blocks_without_matcher}"
    )

    # The RunLens Stop hook is still present.
    stop_cmds = [e["command"] for e in hooks["Stop"][0]["hooks"]]
    assert any("runlens-hook --event Stop --agent claude-code" in c for c in stop_cmds)


def test_installer_installs_trigger_skill_for_supported_agents(tmp_path: Path):
    repo = Path(__file__).resolve().parents[1]
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    (home / ".claude" / "settings.json").write_text("{}\n", encoding="utf-8")
    (home / ".codex").mkdir(parents=True)
    (home / ".codex" / "config.toml").write_text("[hooks.state]\n", encoding="utf-8")
    (home / ".config" / "opencode").mkdir(parents=True)
    (home / ".config" / "opencode" / "opencode.json").write_text(
        '{"plugin":[]}\n',
        encoding="utf-8",
    )
    (home / ".cursor").mkdir(parents=True)

    env = os.environ.copy()
    env["HOME"] = str(home)

    result = subprocess.run(
        ["bash", "scripts/install-agent-hooks.sh"],
        cwd=repo,
        env=env,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr + result.stdout

    targets = [
        home / ".claude" / "skills" / "runlens-artifact-protocol" / "SKILL.md",
        home / ".codex" / "skills" / "runlens-artifact-protocol" / "SKILL.md",
        home
        / ".config"
        / "opencode"
        / "skills"
        / "runlens-artifact-protocol"
        / "SKILL.md",
        home / ".cursor" / "skills" / "runlens-artifact-protocol" / "SKILL.md",
    ]
    for target in targets:
        assert target.exists(), f"missing installed skill: {target}"
        text = target.read_text(encoding="utf-8")
        assert "description: Use when" in text
        assert "long-running" in text
        assert "release" in text
        assert ".agent-artifacts/" in text
