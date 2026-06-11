"""Memory collector — RAM and swap totals/usage."""

from __future__ import annotations

from ..core.models import Section, Status
from ..core.registry import register
from . import _psutil

_GB = 1024 ** 3


def _gb(num_bytes: int) -> float:
    return round(num_bytes / _GB, 2)


@register("memory")
def collect() -> Section:
    ps = _psutil.get()
    if ps is None:
        return Section(
            "memory", "Memory", Status.UNAVAILABLE, {}, [_psutil.MISSING_NOTE]
        )

    vm = ps.virtual_memory()
    data = {
        "total_gb": _gb(vm.total),
        "available_gb": _gb(vm.available),
        "used_gb": _gb(vm.used),
        "percent_used": vm.percent,
    }
    try:
        sw = ps.swap_memory()
        data["swap_total_gb"] = _gb(sw.total)
        data["swap_used_gb"] = _gb(sw.used)
    except Exception:
        pass

    return Section("memory", "Memory", Status.OK, data)
