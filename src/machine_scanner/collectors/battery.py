"""Battery collector — charge, status, and (where exposed) health.

Per-category peripheral collector (ADR-012). A desktop has no battery, so the
*expected* result on much of the fleet is a clean ``unavailable`` — this
collector is the reference for "absent is not an error".

- **Windows** — ``Win32_Battery`` via CIM (charge %, runtime, chemistry). No
  rows → no battery.
- **Linux** — ``/sys/class/power_supply/BAT*`` sysfs (capacity, status,
  manufacturer, model, technology, and design-vs-full energy for a health %).
  No ``BAT*`` node → no battery. No root needed.
- **macOS** — ``system_profiler SPPowerDataType`` (charge, condition, cycle
  count). A desktop Mac reports no battery section.
- **other** — ``unsupported``.

Never raises: the battery-less case is the headline degrade path.
"""

from __future__ import annotations

from typing import Any, Callable

import glob
import os

from ..core.models import Section, Status
from ..core.platform import current_os, run_command
from ..core.registry import register
from . import _smbios

_TITLE = "Battery"

_NO_BATTERY = "no battery present (typical for a desktop)"

# Win32_Battery.BatteryStatus code -> label (the common subset).
_WIN_STATUS: dict[Any, str] = {
    1: "discharging", 2: "on AC", 3: "fully charged", 4: "low",
    5: "critical", 6: "charging", 7: "charging (high)", 8: "charging (low)",
    9: "charging (critical)", 10: "undefined", 11: "partially charged",
}

# Win32_Battery.Chemistry code -> label.
_WIN_CHEMISTRY: dict[Any, str] = {
    1: "other", 2: "unknown", 3: "lead acid", 4: "nickel cadmium",
    5: "nickel metal hydride", 6: "lithium-ion", 7: "zinc air",
    8: "lithium polymer",
}


def _entry(**fields) -> dict:
    return {key: value for key, value in fields.items() if value is not None}


def _section(data: dict, notes: list[str], status: Status = Status.OK) -> Section:
    return Section("battery", _TITLE, status, data, notes)


def _absent() -> Section:
    return _section({"present": False}, [_NO_BATTERY], Status.UNAVAILABLE)


# --------------------------------------------------------------------------- #
# Windows — Win32_Battery via CIM
# --------------------------------------------------------------------------- #

# Wrap in @() + -InputObject so a battery-less box emits "[]" (an empty array)
# rather than nothing — that lets us tell "no battery" (an empty list) apart from
# "the query failed" (no output → run_cim returns None). The accurate degrade
# path matters here: a desktop reporting "no battery present" is the common case.
_PS_BAT = (
    "$rows = @(Get-CimInstance -ClassName Win32_Battery | "
    "Select-Object Name,EstimatedChargeRemaining,BatteryStatus,Chemistry,"
    "EstimatedRunTime,DesignVoltage); "
    "ConvertTo-Json -InputObject $rows -Compress"
)


def _collect_windows() -> Section:
    rows = _smbios.run_cim(_PS_BAT)
    if rows is None:
        return _section({"present": False}, ["could not query Win32_Battery via CIM"], Status.UNAVAILABLE)
    if not rows:
        return _absent()
    row = rows[0]
    charge = row.get("EstimatedChargeRemaining")
    runtime = row.get("EstimatedRunTime")
    data = _entry(
        present=True,
        name=_smbios.clean(row.get("Name")),
        charge_percent=charge if isinstance(charge, (int, float)) else None,
        status=_WIN_STATUS.get(row.get("BatteryStatus")),
        chemistry=_WIN_CHEMISTRY.get(row.get("Chemistry")),
        # Win32 reports 71582788 ("unknown") when on AC — treat as not-a-number.
        runtime_minutes=runtime if isinstance(runtime, int) and runtime < 71582788 else None,
    )
    return _section(data, [])


# --------------------------------------------------------------------------- #
# Linux — /sys/class/power_supply/BAT*
# --------------------------------------------------------------------------- #

_POWER_SUPPLY = "/sys/class/power_supply"


def _read(path: str) -> str | None:
    try:
        with open(path, errors="replace") as handle:
            return handle.read().strip() or None
    except (FileNotFoundError, PermissionError, OSError):
        return None


def _as_int(value: str | None) -> int | None:
    return int(value) if value and value.lstrip("-").isdigit() else None


def _collect_linux(power_supply: str = _POWER_SUPPLY) -> Section:
    bats = sorted(glob.glob(os.path.join(power_supply, "BAT*")))
    if not bats:
        return _absent()
    base = bats[0]
    capacity = _as_int(_read(os.path.join(base, "capacity")))
    full = _as_int(_read(os.path.join(base, "energy_full"))) or _as_int(_read(os.path.join(base, "charge_full")))
    design = _as_int(_read(os.path.join(base, "energy_full_design"))) or _as_int(_read(os.path.join(base, "charge_full_design")))
    health = round(100 * full / design, 1) if full and design else None
    data = _entry(
        present=True,
        name=os.path.basename(base),
        charge_percent=capacity,
        status=(_read(os.path.join(base, "status")) or "").lower() or None,
        manufacturer=_read(os.path.join(base, "manufacturer")),
        model=_read(os.path.join(base, "model_name")),
        technology=_read(os.path.join(base, "technology")),
        health_percent=health,
    )
    return _section(data, [])


# --------------------------------------------------------------------------- #
# macOS — system_profiler SPPowerDataType
# --------------------------------------------------------------------------- #

def _parse_macos(out: str) -> dict | None:
    """Pull charge / condition / cycle count out of SPPowerDataType.

    Returns ``None`` when no battery section is present (a desktop Mac).
    """
    fields: dict[str, tuple[str, Callable[[str], Any]]] = {
        "State of Charge (%)": ("charge_percent", _as_int),
        "Charge Remaining (mAh)": ("charge_remaining_mah", _as_int),
        "Cycle Count": ("cycle_count", _as_int),
        "Condition": ("condition", str),
    }
    data: dict = {}
    saw_battery = False
    for raw in out.splitlines():
        line = raw.strip()
        if line.startswith("Battery Information"):
            saw_battery = True
        if ":" not in line:
            continue
        label, _, value = line.partition(":")
        spec = fields.get(label.strip())
        if spec:
            key, caster = spec
            cast = caster(value.strip())
            if cast not in (None, ""):
                data[key] = cast
    if not saw_battery and not data:
        return None
    data["present"] = True
    return data


def _collect_macos() -> Section:
    out = run_command(["system_profiler", "SPPowerDataType"], timeout=20.0)
    if not out or not out.strip():
        return _section({"present": False}, ["could not query power via system_profiler"], Status.UNAVAILABLE)
    data = _parse_macos(out)
    if data is None:
        return _absent()
    return _section(data, [])


# --------------------------------------------------------------------------- #
# Dispatch
# --------------------------------------------------------------------------- #

@register("battery")
def collect() -> Section:
    system = current_os()
    if system == "windows":
        return _collect_windows()
    if system == "linux":
        return _collect_linux()
    if system == "macos":
        return _collect_macos()
    return Section(
        "battery", _TITLE, Status.UNSUPPORTED, {"present": False},
        [f"battery probing is not implemented for {system!r} yet"],
    )
