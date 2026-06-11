"""Plain-text renderer — the default, human-readable console report.

The data a collector returns is arbitrarily nested (a network interface holds a
list of address dicts; a disk holds a list of partition dicts). The renderer is
fully recursive so any depth stays readable as an indented outline instead of a
Python ``repr`` — lists of records are separated by blank lines, scalars in a
record print as ``key: value``, and an empty list prints ``(none)``.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from ..core.models import Inventory, Status

_STATUS_MARK = {
    Status.OK: "[ok]",
    Status.PARTIAL: "[partial]",
    Status.UNAVAILABLE: "[n/a]",
    Status.UNSUPPORTED: "[todo]",
    Status.ERROR: "[error]",
}

_STEP = 2  # spaces added per nesting level


def _is_mapping(value: Any) -> bool:
    return isinstance(value, Mapping)


def _is_list(value: Any) -> bool:
    # str/bytes are Sequences too — exclude them, they are scalars here.
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes))


def _render_mapping(mapping: Mapping[str, Any], indent: int) -> list[str]:
    """Render a dict as ``key: value`` lines, recursing into nested containers."""
    pad = " " * indent
    lines: list[str] = []
    for key, value in mapping.items():
        if _is_mapping(value) or _is_list(value):
            lines.append(f"{pad}{key}:")
            lines.extend(_render_value(value, indent + _STEP))
        else:
            lines.append(f"{pad}{key}: {value}")
    return lines


def _render_value(value: Any, indent: int) -> list[str]:
    """Render any value, recursing into nested lists/dicts to arbitrary depth."""
    pad = " " * indent
    lines: list[str] = []
    if _is_mapping(value):
        lines.extend(_render_mapping(value, indent))
    elif _is_list(value):
        if not value:
            lines.append(f"{pad}(none)")
        for i, item in enumerate(value):
            if _is_mapping(item):
                if i:  # blank line between records keeps a list of dicts scannable
                    lines.append("")
                lines.extend(_render_mapping(item, indent))
            elif _is_list(item):
                lines.extend(_render_value(item, indent))
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
        out.extend(_render_mapping(sec.data, indent=2))
        for note in sec.notes:
            # keep tracebacks (multi-line) readable, indent the first line only
            out.append(f"  ! {note.splitlines()[0]}")

    out.append("")
    return "\n".join(out)
