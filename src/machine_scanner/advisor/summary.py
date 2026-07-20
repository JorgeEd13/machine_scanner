"""A short, paste-friendly rendering of the fit verdict.

The full scan is for someone reading a report. This is for someone pasting a
dozen lines into a chat window to ask "will this work on my machine?" — so it is
plain text, narrow enough not to wrap, and leads with the answer rather than the
evidence. The model table is deliberately left out: it belongs in the report,
and pasting nine rows buries the one line that matters.

Like the rest of the report layer, this **displays and never computes** — every
number it prints was already decided in :mod:`.fit`.
"""

from __future__ import annotations

from ..core.models import Inventory, Status
from .fit import ADVISOR_NAME, build_section

_WIDTH = 52


def to_summary(inventory: Inventory) -> str:
    """Render the fit verdict for a completed scan as a pasteable block."""
    section = inventory.section(ADVISOR_NAME) or build_section(inventory)
    meta = inventory.meta
    data = section.data

    out = [
        "Local LLM hardware check",
        "-" * _WIDTH,
        f"machine : {meta.get('hostname', '?')}",
        f"os      : {meta.get('os_detail', '?')}",
        f"scanned : {meta.get('scanned_at', '?')}",
        "",
    ]

    if section.status is Status.UNAVAILABLE or not data:
        out.append("Verdict : UNKNOWN — not enough hardware detail to size a model.")
        out.extend(f"  ! {note}" for note in section.notes)
        out.append("")
        return "\n".join(out)

    out.append(f"Verdict : {str(data.get('verdict', '?')).upper()}")
    out.append(f"          {data.get('summary', '')}")
    out.append("")

    model = data.get("recommended_model")
    out.append(f"Best fit: {model}" if model else "Best fit: none — no model in the catalog fits")

    basis = data.get("memory_basis", "")
    out.append(f"Memory  : {data.get('usable_memory_gb')} GB usable ({basis})")

    gpu_name = data.get("gpu_name")
    out.append(f"GPU     : {gpu_name}" if data.get("gpu_accelerated") else "GPU     : none usable — runs on CPU")

    free_disk = data.get("free_disk_gb")
    out.append(f"Disk    : {free_disk:.0f} GB free" if free_disk is not None else "Disk    : unknown")

    cores = data.get("cpu_cores_logical")
    if cores:
        out.append(f"CPU     : {cores} logical cores")

    if section.notes:
        out.append("")
        out.append("Notes:")
        out.extend(f"  - {note}" for note in section.notes)

    out.append("")
    return "\n".join(out)
