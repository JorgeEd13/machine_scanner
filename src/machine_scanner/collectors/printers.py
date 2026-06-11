"""Printers collector — the print queues configured on this machine.

Per-category peripheral collector (ADR-012), a sibling of ``usb`` / ``bluetooth``.
This inventories the *configured* print destinations (local, shared, network),
not physical hardware on a bus — so an absent print spooler / CUPS daemon is the
expected degrade, never an error.

- **Windows** — ``Win32_Printer`` via CIM (Name, Default, PortName, DriverName,
  Shared, Network, WorkOffline).
- **Linux** — ``lpstat -p`` (CUPS queues + state) and ``lpstat -d`` (the system
  default). No ``lpstat`` / no running cupsd → a clean ``unavailable``.
- **macOS** — ``system_profiler SPPrintersDataType``.
- **other** — ``unsupported``.

Never raises: no printers configured, no CUPS daemon, and no print subsystem are
all expected and degrade to ``unavailable`` with an accurate note.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional

from ..core.models import Section, Status
from ..core.platform import current_os, run_command
from ..core.registry import register
from . import _smbios

_TITLE = "Printers"


def _entry(**fields) -> Dict:
    """Build a record, dropping ``None`` fields (booleans like ``default=False``
    are kept — a printer not being the default is meaningful)."""
    return {key: value for key, value in fields.items() if value is not None}


def _finalize(printers: List[Dict], notes: List[str]) -> Section:
    populated = [p for p in printers if p]
    if not populated:
        return Section("printers", _TITLE, Status.UNAVAILABLE, {"printers": []}, notes)
    return Section(
        "printers", _TITLE, Status.OK,
        {"printers": populated, "count": len(populated)}, notes,
    )


# --------------------------------------------------------------------------- #
# Windows — Win32_Printer via CIM
# --------------------------------------------------------------------------- #

# @() + -InputObject so a printer-less box emits "[]" (clean: no printers) rather
# than nothing — distinguishing that from a query failure (run_cim -> None).
_PS_PRINTERS = (
    "$rows = @(Get-CimInstance -ClassName Win32_Printer | Select-Object "
    "Name,Default,PortName,DriverName,Shared,Network,WorkOffline); "
    "ConvertTo-Json -InputObject $rows -Compress"
)


def _as_bool(value: object) -> Optional[bool]:
    return value if isinstance(value, bool) else None


def _collect_windows() -> Section:
    rows = _smbios.run_cim(_PS_PRINTERS)
    if rows is None:
        return Section(
            "printers", _TITLE, Status.UNAVAILABLE, {"printers": []},
            ["could not query printers via CIM (Win32_Printer)"],
        )
    if not rows:
        return Section(
            "printers", _TITLE, Status.UNAVAILABLE, {"printers": []},
            ["no printers configured"],
        )
    printers = [
        _entry(
            name=_smbios.clean(row.get("Name")),
            default=_as_bool(row.get("Default")),
            port=_smbios.clean(row.get("PortName")),
            driver=_smbios.clean(row.get("DriverName")),
            shared=_as_bool(row.get("Shared")),
            network=_as_bool(row.get("Network")),
            offline=_as_bool(row.get("WorkOffline")),
        )
        for row in rows
    ]
    return _finalize(printers, [])


# --------------------------------------------------------------------------- #
# Linux — lpstat -p (queues) + lpstat -d (default)
# --------------------------------------------------------------------------- #

# "printer Office_LaserJet is idle.  enabled since ..." / "printer X disabled ..."
_LPSTAT_P_RE = re.compile(r"^printer\s+(\S+)\s+(.*)$")
# "system default destination: Office_LaserJet"
_LPSTAT_D_RE = re.compile(r"^system default destination:\s*(\S+)")


def _printer_status(rest: str) -> Optional[str]:
    low = rest.lower()
    if "disabled" in low:
        return "disabled"
    if "now printing" in low or "is printing" in low:
        return "printing"
    if "is idle" in low:
        return "idle"
    return None


def _parse_lpstat(p_out: str, default: Optional[str]) -> List[Dict]:
    printers: List[Dict] = []
    for line in p_out.splitlines():
        match = _LPSTAT_P_RE.match(line.strip())
        if not match:
            continue
        name, rest = match.group(1), match.group(2)
        printers.append(
            _entry(
                name=name,
                status=_printer_status(rest),
                default=(name == default) if default else None,
            )
        )
    return printers


def _parse_default(d_out: Optional[str]) -> Optional[str]:
    if not d_out:
        return None
    for line in d_out.splitlines():
        match = _LPSTAT_D_RE.match(line.strip())
        if match:
            return match.group(1)
    return None


def _collect_linux() -> Section:
    p_out = run_command(["lpstat", "-p"])
    if p_out is None:
        return Section(
            "printers", _TITLE, Status.UNAVAILABLE, {"printers": []},
            ["no CUPS / lpstat (printing not configured or cupsd not running)"],
        )
    default = _parse_default(run_command(["lpstat", "-d"]))
    printers = _parse_lpstat(p_out, default)
    if not printers:
        return Section(
            "printers", _TITLE, Status.UNAVAILABLE, {"printers": []},
            ["no printers configured (CUPS has no destinations)"],
        )
    return _finalize(printers, [])


# --------------------------------------------------------------------------- #
# macOS — system_profiler SPPrintersDataType
# --------------------------------------------------------------------------- #

def _parse_macos(out: str) -> List[Dict]:
    """Walk the indented printer headers, pulling Status / Default under each."""
    skip = {"Printers:"}
    printers: List[Dict] = []
    current: Optional[Dict] = None
    for raw in out.splitlines():
        line = raw.strip()
        if not line or line in skip:
            continue
        if line.endswith(":") and ":" not in line[:-1]:
            current = {"name": line[:-1].strip()}
            printers.append(current)
            continue
        if current is None or ":" not in line:
            continue
        label, _, value = line.partition(":")
        label, value = label.strip().lower(), value.strip()
        if label == "status" and value:
            current["status"] = value.lower()
        elif label == "default" and value:
            current["default"] = value.strip().lower() == "yes"
    return [{k: v for k, v in p.items() if v is not None} for p in printers]


def _collect_macos() -> Section:
    out = run_command(["system_profiler", "SPPrintersDataType"], timeout=20.0)
    if not out or not out.strip():
        return Section(
            "printers", _TITLE, Status.UNAVAILABLE, {"printers": []},
            ["could not query printers via system_profiler"],
        )
    return _finalize(_parse_macos(out), [])


# --------------------------------------------------------------------------- #
# Dispatch
# --------------------------------------------------------------------------- #

@register("printers")
def collect() -> Section:
    system = current_os()
    if system == "windows":
        return _collect_windows()
    if system == "linux":
        return _collect_linux()
    if system == "macos":
        return _collect_macos()
    return Section(
        "printers", _TITLE, Status.UNSUPPORTED, {"printers": []},
        [f"printer probing is not implemented for {system!r} yet"],
    )
