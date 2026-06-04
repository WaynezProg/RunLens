from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, PackageLoader

from runlens.models import ArtifactSpec, RunState
from runlens.store import ARTIFACTS_DIR, load_spec, load_state


def template_env() -> Environment:
    return Environment(
        loader=PackageLoader("runlens", "templates"),
        autoescape=True,
    )


def render_report(
    base: Path,
    output_path: Path,
    spec: ArtifactSpec | None = None,
    state: RunState | None = None,
    banner: str | None = None,
) -> Path:
    resolved_spec = spec or load_spec(base)
    resolved_state = state or load_state(base)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    html = template_env().get_template("report.html.j2").render(
        spec=resolved_spec,
        state=resolved_state,
        banner=banner,
    )
    output_path.write_text(html, encoding="utf-8")
    return output_path


def render_working_report(
    base: Path,
    banner: str | None = None,
    state: RunState | None = None,
    spec: ArtifactSpec | None = None,
) -> Path:
    return render_report(
        base=base,
        output_path=base / ARTIFACTS_DIR / "working" / "report.html",
        spec=spec,
        state=state,
        banner=banner,
    )


def checkpoint_report_path(base: Path, timestamp: str) -> Path:
    return base / ARTIFACTS_DIR / "checkpoints" / f"checkpoint-{timestamp}.html"


def final_report_path(base: Path) -> Path:
    return base / ARTIFACTS_DIR / "deliverables" / "final.html"


def render_checkpoint_report(
    base: Path,
    reason: str,
    timestamp: str,
    state: RunState | None = None,
) -> Path:
    return render_report(
        base=base,
        output_path=checkpoint_report_path(base, timestamp),
        state=state,
        banner=f"Checkpoint: {reason}",
    )


def render_final_report(base: Path, state: RunState | None = None) -> Path:
    return render_report(
        base=base,
        output_path=final_report_path(base),
        state=state,
        banner="Final: all required acceptance criteria passed.",
    )
