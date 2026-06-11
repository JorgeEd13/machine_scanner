"""Input devices collector — keyboards and pointing devices.

Per-category peripheral collector (ADR-012). This deliberately overlaps the
``usb`` collector for USB keyboards/mice, but adds the *built-in* and non-USB
inputs (laptop keyboard, PS/2, I2C touchpad) that never show up on the USB bus.

- **Windows** — ``Win32_Keyboard`` + ``Win32_PointingDevice`` via CIM.
- **Linux** — ``/proc/bus/input/devices`` (the kernel's input registry); each
  ``N:`` block has an ``N: Name="..."`` line and ``H: Handlers=`` that tells us
  whether it is a keyboard / mouse. No root needed.
- **macOS** — ``system_profiler`` has no dedicated input type; inputs surface
  under ``usb`` instead, so this honestly reports ``unsupported`` with a pointer.
- **other** — ``unsupported``.

Never raises.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional

from ..core.models import Section, Status
from ..core.platform import current_os, run_command
from ..core.registry import register
from . import _smbios

_TITLE = "Input Devices"


def _entry(**fields) -> Dict:
    return {key: value for key, value in fields.items() if value is not None}


def _finalize(devices: List[Dict], notes: List[str]) -> Section:
    populated = [d for d in devices if d]
    if not populated:
        return Section("input", _TITLE, Status.UNAVAILABLE, {"devices": []}, notes)
    return Section(
        "input", _TITLE, Status.OK,
        {"devices": populated, "count": len(populated)}, notes,
    )


# --------------------------------------------------------------------------- #
# Windows — Win32_Keyboard + Win32_PointingDevice via CIM
# --------------------------------------------------------------------------- #

_PS_INPUT = (
    "$kb = Get-CimInstance Win32_Keyboard | "
    "Select-Object @{n='kind';e={'keyboard'}},Name,Description,Manufacturer; "
    "$pt = Get-CimInstance Win32_PointingDevice | "
    "Select-Object @{n='kind';e={'pointing'}},Name,Description,Manufacturer; "
    "@($kb) + @($pt) | ConvertTo-Json -Compress"
)


def _collect_windows() -> Section:
    rows = _smbios.run_cim(_PS_INPUT)
    if rows is None:
        return Section(
            "input", _TITLE, Status.UNAVAILABLE, {"devices": []},
            ["could not query input devices via CIM"],
        )
    devices = [
        _entry(
            kind=row.get("kind"),
            name=_smbios.clean(row.get("Name")) or _smbios.clean(row.get("Description")),
            manufacturer=_smbios.clean(row.get("Manufacturer")),
        )
        for row in rows
    ]
    return _finalize(devices, [])


# --------------------------------------------------------------------------- #
# Linux — /proc/bus/input/devices
# --------------------------------------------------------------------------- #

_PROC_INPUT = "/proc/bus/input/devices"
_NAME_RE = re.compile(r'^N:\s*Name="(.*)"')
_HANDLERS_RE = re.compile(r"^H:\s*Handlers=(.*)")


def _classify(handlers: str) -> Optional[str]:
    tokens = handlers.split()
    if any(t.startswith("kbd") for t in tokens):
        return "keyboard"
    if any(t.startswith("mouse") for t in tokens):
        return "pointing"
    return None


def _parse_proc_input(text: str) -> List[Dict]:
    """Parse the blank-line-separated device blocks; keep keyboards/pointers."""
    devices: List[Dict] = []
    name: Optional[str] = None
    kind: Optional[str] = None
    for line in text.splitlines():
        if not line.strip():  # block separator
            if name and kind:
                devices.append(_entry(kind=kind, name=name))
            name, kind = None, None
            continue
        name_match = _NAME_RE.match(line)
        if name_match:
            name = name_match.group(1).strip() or None
            continue
        handlers_match = _HANDLERS_RE.match(line)
        if handlers_match:
            kind = _classify(handlers_match.group(1))
    if name and kind:  # trailing block with no final blank line
        devices.append(_entry(kind=kind, name=name))
    return devices


def _collect_linux(proc_input: str = _PROC_INPUT) -> Section:
    try:
        with open(proc_input, "r", errors="replace") as handle:
            text = handle.read()
    except (FileNotFoundError, PermissionError, OSError):
        return Section(
            "input", _TITLE, Status.UNAVAILABLE, {"devices": []},
            [f"no input registry at {proc_input}"],
        )
    return _finalize(_parse_proc_input(text), [])


# --------------------------------------------------------------------------- #
# Dispatch
# --------------------------------------------------------------------------- #

@register("input")
def collect() -> Section:
    system = current_os()
    if system == "windows":
        return _collect_windows()
    if system == "linux":
        return _collect_linux()
    if system == "macos":
        return Section(
            "input", _TITLE, Status.UNSUPPORTED, {"devices": []},
            ["macOS has no dedicated input type; input devices appear under 'usb'"],
        )
    return Section(
        "input", _TITLE, Status.UNSUPPORTED, {"devices": []},
        [f"input-device probing is not implemented for {system!r} yet"],
    )
