"""Peripherals collector — USB devices, monitors, input devices.

Placeholder: this needs OS-specific enumeration (Windows WMI/CIM, Linux
``lsusb``/sysfs, macOS ``system_profiler``) and is scheduled for ROADMAP F3. It
already registers so it shows up in ``--list`` and in the report as a known,
not-yet-implemented section — making the roadmap visible in the output itself.
"""

from __future__ import annotations

from ..core.models import Section, Status
from ..core.registry import register


@register("peripherals")
def collect() -> Section:
    return Section(
        "peripherals",
        "Peripherals",
        Status.UNSUPPORTED,
        {},
        ["USB / monitor / input-device enumeration is planned (see ROADMAP F3)"],
    )
