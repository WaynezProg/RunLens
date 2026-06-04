from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import vl_convert as vlc

from runlens.models import MetadataItem
from runlens.store import artifacts_root

MAX_TABLE_ROWS = 50


@dataclass(frozen=True)
class RenderedChart:
    """A chart prepared for the template: either inline SVG or a fallback."""

    title: str
    type: str
    status: str
    path: str
    svg: str | None = None
    fallback_reason: str | None = None
    table_headers: list[str] | None = None
    table_rows: list[list[str]] | None = None


def _resolve_spec_file(base: Path, rel_path: str) -> Path | None:
    # charts[].path is base-relative (".agent-artifacts/...") in some specs and
    # artifacts-root-relative ("working/...") in others; accept both.
    for candidate in (base / rel_path, artifacts_root(base) / rel_path):
        if candidate.is_file():
            return candidate
    return None


def _inline_table(spec: object) -> tuple[list[str], list[list[str]]] | None:
    if not isinstance(spec, dict):
        return None
    data = spec.get("data")
    values = data.get("values") if isinstance(data, dict) else None
    if not isinstance(values, list):
        return None
    rows = [row for row in values if isinstance(row, dict)]
    if not rows:
        return None

    headers: list[str] = []
    for row in rows:
        for key in row:
            if str(key) not in headers:
                headers.append(str(key))
    table_rows = [
        ["" if row.get(header) is None else str(row.get(header)) for header in headers]
        for row in rows[:MAX_TABLE_ROWS]
    ]
    return headers, table_rows


def render_chart(base: Path, chart: MetadataItem) -> RenderedChart:
    """Pre-render a Vega-Lite spec to inline SVG, falling back without raising.

    Validation is delegated to vl-convert: a spec that converts is valid; any
    failure (missing file, bad JSON, schema/mark errors) yields a fallback with a
    data table (when inline `data.values` exist) and a link to the spec.
    """

    def fallback(reason: str, spec: object = None) -> RenderedChart:
        table = _inline_table(spec)
        return RenderedChart(
            title=chart.title,
            type=chart.type,
            status=chart.status,
            path=chart.path,
            fallback_reason=reason,
            table_headers=table[0] if table else None,
            table_rows=table[1] if table else None,
        )

    spec_file = _resolve_spec_file(base, chart.path)
    if spec_file is None:
        return fallback(f"Spec file not found: {chart.path}")

    try:
        spec = json.loads(spec_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return fallback(f"Invalid JSON: {error}")

    try:
        svg = vlc.vegalite_to_svg(spec)
    except Exception as error:  # vl-convert raises ValueError on invalid specs
        reason = str(error).splitlines()[0] if str(error).strip() else error.__class__.__name__
        return fallback(f"Vega-Lite render failed: {reason}", spec)

    return RenderedChart(
        title=chart.title,
        type=chart.type,
        status=chart.status,
        path=chart.path,
        svg=svg,
    )
