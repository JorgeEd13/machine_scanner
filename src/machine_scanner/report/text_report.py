"""Plain-text renderer — the default, human-readable console report."""

from __future__ import annotations

from typing import Any

from ..core.models import Inventory, Status

_STATUS_MARK = {
    Status.OK: "[ok]",
    Status.PARTIAL: "[partial]",
    Status.UNAVAILABLE: "[n/a]",
    Status.UNSUPPORTED: "[todo]",
    Status.ERROR: "[error]",
}


def _render_value(value: Any, indent: int) -> list[str]:
    """Render a single value, recursing into lists of dicts (e.g. partitions)."""
    pad = " " * indent
    lines: list[str] = []
    if isinstance(value, list):
        if not value:
            lines.append(f"{pad}(none)")
        for i, item in enumerate(value):
            if isinstance(item, dict):
                if i:
                    lines.append("")
                for k, v in item.items():
                    lines.append(f"{pad}{k}: {v}")
            else:
                lines.append(f"{pad}- {item}")
    else:
        lines.append(f"{pad}{value}")
    return lines


def to_text(inventory: Inventory) -> str:
    out: list[str] = []
    meta = inventory.meta
    out.append("=" * 64)
    out.append(f"  machine_scanner v{meta.get('version', '?')} — machine inventory")
    out.append("=" * 64)
    out.append(f"host     : {meta.get('hostname')}  ({meta.get('user')})")
    out.append(f"os       : {meta.get('os_detail')}")
    out.append(f"scanned  : {meta.get('scanned_at')}")
    out.append(f"elevated : {meta.get('elevated')}")

    for sec in inventory.sections:
        out.append("")
        mark = _STATUS_MARK.get(sec.status, "")
        out.append(f"[{sec.title}] {mark}")
        for key, value in sec.data.items():
            if isinstance(value, (list, dict)):
                out.append(f"  {key}:")
                out.extend(_render_value(value, indent=4))
            else:
                out.append(f"  {key}: {value}")
        for note in sec.notes:
            # keep tracebacks (multi-line) readable, indent the first line only
            out.append(f"  ! {note.splitlines()[0]}")

    out.append("")
    return "\n".join(out)
