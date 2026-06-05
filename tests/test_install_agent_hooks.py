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
