"""Hook adapter: normalize agent lifecycle events and append to hooks.jsonl."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from runlens.store import now_utc


def _get_git_repo() -> str | None:
    """Return owner/repo if in a git repo, else None."""
    try:
        remote = subprocess.check_output(
            ["git", "remote", "get-url", "origin"],
            cwd=Path.cwd(),
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=5,
        ).strip()
        if remote.startswith("git@"):
            parts = remote.split(":")
            if len(parts) == 2:
                return parts[1].removesuffix(".git")
        elif remote.startswith("https://") or remote.startswith("http://"):
            path = remote.split("//", 1)[1]
            return path.removesuffix(".git")
    except (subprocess.SubprocessError, FileNotFoundError, OSError, TimeoutError):
        pass
    return None


_SECRET_KEYS = frozenset({"authorization", "api_key", "apikey", "secret", "token", "password", "bearer"})


def _sanitize(obj: dict | list | str | int | float | bool | None) -> object:
    """Remove secrets from payload recursively."""
    if isinstance(obj, dict):
        return {
            k: _sanitize(v) for k, v in obj.items() if k.lower() not in _SECRET_KEYS
        }
    if isinstance(obj, list):
        return [_sanitize(item) for item in obj]
    return obj


def _hooks_jsonl_path(data_home: str | None = None) -> Path:
    """Return path to hooks.jsonl, respecting XDG_DATA_HOME."""
    base = Path(data_home) if data_home else Path(
        os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share"))
    )
    hooks_dir = base / "runlens"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    return hooks_dir / "hooks.jsonl"


def normalize_and_append(
    event: str,
    agent: str,
    stdin_data: str,
    data_home: str | None = None,
) -> dict:
    """Normalize a lifecycle event and append to hooks.jsonl.

    Returns the normalized event dict.
    """
    try:
        raw_payload = json.loads(stdin_data) if stdin_data.strip() else {}
    except json.JSONDecodeError:
        raw_payload = {"_parse_error": True, "_raw": stdin_data[:1000]}

    sanitized = _sanitize(raw_payload) if isinstance(raw_payload, dict) else {"_non_dict": True}

    normalized = {
        "ts": now_utc(),
        "cwd": str(Path.cwd()),
        "git_repo": _get_git_repo(),
        "agent": agent,
        "event": event,
        "raw": sanitized,
    }

    hooks_path = _hooks_jsonl_path(data_home)
    with open(hooks_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(normalized, ensure_ascii=True) + "\n")

    return normalized
