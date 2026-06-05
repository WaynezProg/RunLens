"""Contract tests for the runlens-hook shell wrapper.

A lifecycle hook is best-effort telemetry. It MUST never crash or block the
host agent. Concretely: it always exits 0 and writes nothing to stdout, even
when its runtime (uv / runlens) cannot be found — which is exactly what happens
when a GUI-launched agent (e.g. Cursor IDE) spawns the hook with a minimal PATH
that lacks Homebrew/mise.
"""
import os
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
WRAPPER = REPO / "scripts" / "runlens-hook"

# Simulates the environment a GUI app passes to spawned processes on macOS:
# no Homebrew, no mise — so `uv` and `runlens` are not on PATH.
GUI_MINIMAL_PATH = "/usr/bin:/bin:/usr/sbin:/sbin"


def _run_wrapper(path_value: str, data_home: Path, stdin: str = "{}"):
    env = os.environ.copy()
    env["PATH"] = path_value
    env["XDG_DATA_HOME"] = str(data_home)  # keep test events out of the real log
    return subprocess.run(
        ["bash", str(WRAPPER), "--event", "Test", "--agent", "cursor"],
        input=stdin,
        text=True,
        capture_output=True,
        env=env,
        timeout=60,
    )


def test_wrapper_is_failsafe_under_gui_minimal_path(tmp_path: Path):
    result = _run_wrapper(GUI_MINIMAL_PATH, tmp_path / "data")
    assert result.returncode == 0, f"must exit 0; stderr={result.stderr!r}"
    assert result.stdout == "", f"stdout must be empty; got {result.stdout!r}"


def test_wrapper_is_failsafe_with_full_path(tmp_path: Path):
    result = _run_wrapper(os.environ.get("PATH", ""), tmp_path / "data")
    assert result.returncode == 0, f"must exit 0; stderr={result.stderr!r}"
    assert result.stdout == "", f"stdout must be empty; got {result.stdout!r}"


def test_wrapper_consumes_stdin_without_error(tmp_path: Path):
    # Agents pipe JSON to the hook; the wrapper must drain stdin and still
    # honour the contract regardless of payload content.
    payload = '{"session_id": "abc", "nested": {"token": "should-be-stripped"}}'
    result = _run_wrapper(os.environ.get("PATH", ""), tmp_path / "data", stdin=payload)
    assert result.returncode == 0, f"stderr={result.stderr!r}"
    assert result.stdout == ""
