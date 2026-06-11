"""Bluetooth collector — local radio(s) and paired/known remote devices.

Per-category peripheral collector (ADR-012), a sibling of ``usb`` / ``audio``.
Bluetooth has two genuinely different levels and the report keeps them apart
(ADR-014): **adapters** (the local radio, ``adapter``-level) and **devices**
(paired / known remote peripherals, ``device``-level). A box with a radio but no
paired devices is still ``ok`` (adapters non-empty); a box with neither degrades
to a clean ``unavailable``.

- **Windows** — ``Win32_PnPEntity`` filtered to ``PNPClass='Bluetooth'`` via CIM
  (the same enumerator-filter shape as ``usb``); each row is split into a remote
  device (``PNPDeviceID`` carries ``DEV_<mac>``) or the local adapter.
- **Linux** — ``bluetoothctl devices`` for the paired/known list (device-level)
  and ``/sys/class/bluetooth/hci*`` for the radios (adapter-level). ``bluetoothctl``
  resolves remote names that sysfs alone can't (ADR-014); when it is absent or no
  controller is up, the adapters still come from sysfs with a note.
- **macOS** — ``system_profiler SPBluetoothDataType`` (a nested controller block
  plus Connected / Not Connected device groups).
- **other** — ``unsupported``.

Never raises: no radio, no service, and no paired devices are all expected and
degrade to ``unavailable`` with an accurate note.
"""

from __future__ import annotations

import os
import re
from typing import Dict, List, Optional, Tuple

from ..core.models import Section, Status
from ..core.platform import current_os, run_command
from ..core.registry import register
from . import _smbios

_TITLE = "Bluetooth"

# BTHENUM\DEV_AABBCCDDEEFF\... — a remote/paired device id carries the peer MAC.
_BTHENUM_DEV_RE = re.compile(r"DEV_([0-9A-Fa-f]{12})")
# bluetoothctl line: "Device AA:BB:CC:DD:EE:FF My Headphones"
_BT_DEVICE_RE = re.compile(r"^Device\s+([0-9A-Fa-f:]{17})\s*(.*)$")


def _entry(**fields) -> Dict:
    """Build a record, dropping empty fields."""
    return {key: value for key, value in fields.items() if value is not None}


def _format_mac(hex12: str) -> str:
    """'aabbccddeeff' -> 'aa:bb:cc:dd:ee:ff' (lower-case)."""
    h = hex12.lower()
    return ":".join(h[i : i + 2] for i in range(0, 12, 2))


def _finalize(adapters: List[Dict], devices: List[Dict], notes: List[str]) -> Section:
    adapters = [a for a in adapters if a]
    devices = [d for d in devices if d]
    if not adapters and not devices:
        return Section(
            "bluetooth", _TITLE, Status.UNAVAILABLE,
            {"adapters": [], "devices": []}, notes,
        )
    data = {
        "adapters": adapters,
        "devices": devices,
        "adapter_count": len(adapters),
        "device_count": len(devices),
    }
    return Section("bluetooth", _TITLE, Status.OK, data, notes)


# --------------------------------------------------------------------------- #
# Windows — Win32_PnPEntity (Bluetooth class) via CIM
# --------------------------------------------------------------------------- #

# Wrap in @() + -InputObject so a Bluetooth-less box emits "[]" (clean: no
# Bluetooth-class devices) rather than nothing — telling that apart from a query
# failure (no output -> run_cim returns None), the battery-collector pattern.
_PS_BT = (
    "$rows = @(Get-CimInstance -ClassName Win32_PnPEntity | "
    "Where-Object { $_.PNPClass -eq 'Bluetooth' } | "
    "Select-Object Name,Manufacturer,PNPDeviceID); "
    "ConvertTo-Json -InputObject $rows -Compress"
)


def _classify_windows(rows: List[Dict]) -> Tuple[List[Dict], List[Dict]]:
    """Split Bluetooth-class PnP rows into (adapters, paired devices).

    A remote/paired device carries ``DEV_<mac>`` in its ``PNPDeviceID``. Service
    /profile sub-nodes (``BTHENUM\\{guid}_...`` with no ``DEV_``) are noise and
    dropped; everything else is the local radio (adapter).
    """
    adapters: List[Dict] = []
    devices: List[Dict] = []
    for row in rows:
        dev_id = row.get("PNPDeviceID")
        dev_id = dev_id if isinstance(dev_id, str) else ""
        name = _smbios.clean(row.get("Name"))
        manufacturer = _smbios.clean(row.get("Manufacturer"))
        mac_match = _BTHENUM_DEV_RE.search(dev_id)
        if mac_match:
            devices.append(
                _entry(name=name, address=_format_mac(mac_match.group(1)),
                       manufacturer=manufacturer)
            )
        elif dev_id.upper().startswith("BTHENUM"):
            continue  # a Bluetooth service/profile node, not a device or radio
        else:
            adapters.append(_entry(name=name, manufacturer=manufacturer))
    return adapters, devices


def _collect_windows() -> Section:
    rows = _smbios.run_cim(_PS_BT)
    if rows is None:
        return Section(
            "bluetooth", _TITLE, Status.UNAVAILABLE,
            {"adapters": [], "devices": []},
            ["could not enumerate Bluetooth via CIM (Win32_PnPEntity)"],
        )
    if not rows:
        return Section(
            "bluetooth", _TITLE, Status.UNAVAILABLE,
            {"adapters": [], "devices": []},
            ["no Bluetooth-class devices present (no radio or it is disabled)"],
        )
    adapters, devices = _classify_windows(rows)
    return _finalize(adapters, devices, [])


# --------------------------------------------------------------------------- #
# Linux — bluetoothctl devices + /sys/class/bluetooth adapters
# --------------------------------------------------------------------------- #

_SYSFS_BT = "/sys/class/bluetooth"


def _read(path: str) -> Optional[str]:
    try:
        with open(path, "r", errors="replace") as handle:
            return handle.read().strip() or None
    except (FileNotFoundError, PermissionError, OSError):
        return None


def _parse_bluetoothctl(out: str) -> List[Dict]:
    devices: List[Dict] = []
    for line in out.splitlines():
        match = _BT_DEVICE_RE.match(line.strip())
        if not match:
            continue
        address, name = match.group(1).lower(), match.group(2).strip()
        devices.append(_entry(name=name or None, address=address))
    return devices


def _read_sysfs_adapters(root: str = _SYSFS_BT) -> List[Dict]:
    """List hciX radios under /sys/class/bluetooth (adapter-level)."""
    if not os.path.isdir(root):
        return []
    adapters: List[Dict] = []
    for name in sorted(os.listdir(root)):
        if not name.startswith("hci"):
            continue
        address = _read(os.path.join(root, name, "address"))
        adapters.append(_entry(name=name, address=address.lower() if address else None))
    return adapters


def _collect_linux(sysfs_bt: str = _SYSFS_BT) -> Section:
    adapters = _read_sysfs_adapters(sysfs_bt)
    notes: List[str] = []
    out = run_command(["bluetoothctl", "devices"])
    if out and out.strip():
        devices = _parse_bluetoothctl(out)
    else:
        devices = []
        if adapters:
            notes.append(
                "bluetoothctl unavailable or no controller up; "
                "adapters from /sys/class/bluetooth only (no paired-device list)"
            )
    if not adapters and not devices:
        return Section(
            "bluetooth", _TITLE, Status.UNAVAILABLE,
            {"adapters": [], "devices": []},
            ["no Bluetooth stack (no /sys/class/bluetooth adapters and no "
             "bluetoothctl devices) — no radio or service"],
        )
    return _finalize(adapters, devices, notes)


# --------------------------------------------------------------------------- #
# macOS — system_profiler SPBluetoothDataType
# --------------------------------------------------------------------------- #

def _parse_macos(out: str) -> Tuple[List[Dict], List[Dict]]:
    """Lift the controller block and the Connected / Not Connected device groups.

    ``SPBluetoothDataType`` nests a ``Bluetooth Controller:`` block (the adapter)
    and one or more device groups (``Connected:`` / ``Not Connected:``); inside a
    group each indented ``Name:`` header starts a device, with ``Address:`` below.
    """
    adapters: List[Dict] = []
    devices: List[Dict] = []
    section: Optional[str] = None  # "controller" | "devices"
    current_adapter: Optional[Dict] = None
    current_device: Optional[Dict] = None
    for raw in out.splitlines():
        line = raw.strip()
        if not line:
            continue
        low = line.lower()
        if low.startswith("bluetooth controller"):
            section, current_adapter = "controller", {}
            adapters.append(current_adapter)
            continue
        if low.startswith(("connected", "not connected", "devices (")):
            section, current_device = "devices", None
            continue
        if section == "controller" and current_adapter is not None and ":" in line:
            label, _, value = line.partition(":")
            label, value = label.strip().lower(), value.strip()
            if label == "address" and value:
                current_adapter["address"] = value.lower()
            elif label == "name" and value:
                current_adapter["name"] = value
            continue
        if section == "devices":
            if line.endswith(":") and ":" not in line[:-1]:
                current_device = {"name": line[:-1].strip()}
                devices.append(current_device)
                continue
            if current_device is not None and ":" in line:
                label, _, value = line.partition(":")
                if label.strip().lower() == "address" and value.strip():
                    current_device["address"] = value.strip().lower()
    adapters = [{k: v for k, v in a.items() if v} for a in adapters]
    devices = [{k: v for k, v in d.items() if v} for d in devices]
    return adapters, devices


def _collect_macos() -> Section:
    out = run_command(["system_profiler", "SPBluetoothDataType"], timeout=20.0)
    if not out or not out.strip():
        return Section(
            "bluetooth", _TITLE, Status.UNAVAILABLE,
            {"adapters": [], "devices": []},
            ["could not query Bluetooth via system_profiler"],
        )
    adapters, devices = _parse_macos(out)
    return _finalize(adapters, devices, [])


# --------------------------------------------------------------------------- #
# Dispatch
# --------------------------------------------------------------------------- #

@register("bluetooth")
def collect() -> Section:
    system = current_os()
    if system == "windows":
        return _collect_windows()
    if system == "linux":
        return _collect_linux()
    if system == "macos":
        return _collect_macos()
    return Section(
        "bluetooth", _TITLE, Status.UNSUPPORTED,
        {"adapters": [], "devices": []},
        [f"Bluetooth probing is not implemented for {system!r} yet"],
    )
