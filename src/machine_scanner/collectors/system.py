"""System / OS collector — stdlib only, so it always returns something.

This is the one collector with no external dependency: it works on the system
Python before anything is installed, which makes it a reliable smoke test that
the registry + reporting pipeline is wired up correctly.
"""

from __future__ import annotations

from typing import Any

import datetime as _dt
import platform

from ..core import platform as plat
from ..core.models import Section, Status
from ..core.registry import register
from . import _psutil


@register("system")
def collect() -> Section:
    data: dict[str, Any] = {
        "os": plat.current_os(),
        "system": platform.system(),
        "release": platform.release(),
        "version": platform.version(),
        "machine": platform.machine(),
        "architecture": platform.architecture()[0],
        "processor": platform.processor() or None,
        "python_version": platform.python_version(),
        "elevated": plat.is_admin(),
    }

    notes = []
    ps = _psutil.get()
    if ps is not None:
        try:
            boot = _dt.datetime.fromtimestamp(ps.boot_time())
            data["boot_time"] = boot.isoformat(timespec="seconds")
            data["uptime_hours"] = round(
                (_dt.datetime.now() - boot).total_seconds() / 3600, 1
            )
        except Exception:
            notes.append("could not read boot time")
    else:
        notes.append(_psutil.MISSING_NOTE)

    return Section("system", "System", Status.OK, data, notes)
