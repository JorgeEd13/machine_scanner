"""CPU collector — core counts, frequency, a quick utilization sample."""

from __future__ import annotations

import platform

from ..core.models import Section, Status
from ..core.registry import register
from . import _psutil


@register("cpu")
def collect() -> Section:
    data = {
        "name": platform.processor() or platform.machine() or None,
        "architecture": platform.machine(),
    }
    notes = []

    ps = _psutil.get()
    if ps is None:
        import os

        data["cores_logical"] = os.cpu_count()
        notes.append(_psutil.MISSING_NOTE)
        return Section("cpu", "CPU", Status.PARTIAL, data, notes)

    data["cores_physical"] = ps.cpu_count(logical=False)
    data["cores_logical"] = ps.cpu_count(logical=True)
    try:
        freq = ps.cpu_freq()
        if freq:
            data["frequency_mhz_current"] = round(freq.current, 0)
            data["frequency_mhz_max"] = round(freq.max, 0) or None
    except Exception:
        notes.append("frequency not available on this platform")

    # A short, non-blocking sample. interval=0.2 keeps the whole scan snappy.
    try:
        data["usage_percent"] = ps.cpu_percent(interval=0.2)
    except Exception:
        notes.append("usage sample unavailable")

    return Section("cpu", "CPU", Status.OK, data, notes)
