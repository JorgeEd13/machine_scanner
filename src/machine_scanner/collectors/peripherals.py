"""Peripherals collector — USB devices (ROADMAP F3, first category).

The first peripheral category: the USB devices attached to this machine. Like
the F2 deep collectors, the source is chosen per-OS and the result is normalized
to a single shape — a flat list of ``{name, vendor_id, product_id,
manufacturer}`` records, with the **VID:PID pair** as the stable cross-OS
identity (see ADR-011).

- **Windows** — ``Win32_PnPEntity`` via CIM, filtered to ``PNPDeviceID`` rows
  under the ``USB`` enumerator; VID/PID parsed out of that device ID.
- **Linux** — ``lsusb`` (it resolves human device *names* that raw IDs can't),
  falling back to ``/sys/bus/usb/devices`` when ``usbutils`` is absent (a
  degraded, names-poorer path — same judgement as ADR-010's GPU enumerator).
- **macOS** — ``system_profiler SPUSBDataType``.
- **other** — ``unsupported``.

Needs no elevation on any OS. Never raises for an expected-absent case (no USB
host controller exposed — e.g. WSL2 has neither ``lsusb`` nor a populated
``/sys/bus/usb`` — degrades to ``unavailable`` with a note).
"""

from __future__ import annotations

import os
import re
from typing import Dict, List, Optional, Tuple

from ..core.models import Section, Status
from ..core.platform import current_os, run_command
from ..core.registry import register
from . import _smbios

_TITLE = "Peripherals"

# USB\VID_8087&PID_0024\... — VID/PID live in the first segment of a USB device
# ID on both Windows (PNPDeviceID) and sysfs modaliases. Hubs / root hubs have
# no VID&PID segment, so both groups are optional.
_VIDPID_RE = re.compile(r"VID_([0-9A-Fa-f]{4}).*?PID_([0-9A-Fa-f]{4})")

# lsusb line: "Bus 002 Device 003: ID 8087:0024 Intel Corp. Integrated Hub"
_LSUSB_RE = re.compile(
    r"^Bus\s+\d+\s+Device\s+\d+:\s+ID\s+([0-9a-fA-F]{4}):([0-9a-fA-F]{4})\s*(.*)$"
)


def _entry(**fields) -> Dict:
    """Build a device record, dropping empty fields."""
    return {key: value for key, value in fields.items() if value is not None}


def _finalize(devices: List[Dict], notes: List[str]) -> Section:
    populated = [d for d in devices if d]
    if not populated:
        return Section(
            "peripherals", _TITLE, Status.UNAVAILABLE, {"usb": []}, notes
        )
    data = {"usb": populated, "count": len(populated)}
    return Section("peripherals", _TITLE, Status.OK, data, notes)


# --------------------------------------------------------------------------- #
# Windows — Win32_PnPEntity (USB enumerator) via CIM
# --------------------------------------------------------------------------- #

_PS_USB = (
    "Get-CimInstance -ClassName Win32_PnPEntity | "
    "Where-Object { $_.PNPDeviceID -like 'USB\\*' } | "
    "Select-Object Name,Manufacturer,PNPDeviceID | ConvertTo-Json -Compress"
)


def _vid_pid(device_id: object) -> Tuple[Optional[str], Optional[str]]:
    """Extract a lower-cased VID/PID pair from a USB device id, if present."""
    if not isinstance(device_id, str):
        return None, None
    match = _VIDPID_RE.search(device_id)
    if not match:
        return None, None
    return match.group(1).lower(), match.group(2).lower()


def _collect_windows() -> Section:
    rows = _smbios.run_cim(_PS_USB)
    if rows is None:
        return Section(
            "peripherals", _TITLE, Status.UNAVAILABLE, {"usb": []},
            ["could not enumerate USB devices via CIM (Win32_PnPEntity)"],
        )
    devices: List[Dict] = []
    for row in rows:
        vid, pid = _vid_pid(row.get("PNPDeviceID"))
        devices.append(
            _entry(
                name=_smbios.clean(row.get("Name")),
                manufacturer=_smbios.clean(row.get("Manufacturer")),
                vendor_id=vid,
                product_id=pid,
            )
        )
    return _finalize(devices, [])


# --------------------------------------------------------------------------- #
# Linux — lsusb, with a /sys/bus/usb/devices fallback
# --------------------------------------------------------------------------- #

_SYSFS_USB = "/sys/bus/usb/devices"


def _parse_lsusb(out: str) -> List[Dict]:
    devices: List[Dict] = []
    for line in out.splitlines():
        match = _LSUSB_RE.match(line.strip())
        if not match:
            continue
        vid, pid, name = match.group(1).lower(), match.group(2).lower(), match.group(3).strip()
        devices.append(_entry(name=name or None, vendor_id=vid, product_id=pid))
    return devices


def _read_sysfs_file(path: str) -> Optional[str]:
    try:
        with open(path, "r", errors="replace") as handle:
            return handle.read().strip() or None
    except (FileNotFoundError, PermissionError, OSError):
        return None


def _parse_sysfs_usb(root: str = _SYSFS_USB) -> List[Dict]:
    """Read VID/PID/names from the device dirs under /sys/bus/usb/devices.

    Interface nodes (names containing ``:``) carry no ``idVendor`` and are
    skipped; only true device nodes expose ``idVendor`` / ``idProduct``.
    """
    if not os.path.isdir(root):
        return []
    devices: List[Dict] = []
    for name in sorted(os.listdir(root)):
        if ":" in name:  # interface, not a device
            continue
        base = os.path.join(root, name)
        vid = _read_sysfs_file(os.path.join(base, "idVendor"))
        pid = _read_sysfs_file(os.path.join(base, "idProduct"))
        if not vid or not pid:
            continue
        product = _read_sysfs_file(os.path.join(base, "product"))
        manufacturer = _read_sysfs_file(os.path.join(base, "manufacturer"))
        devices.append(
            _entry(
                name=product,
                manufacturer=manufacturer,
                vendor_id=vid.lower(),
                product_id=pid.lower(),
            )
        )
    return devices


def _collect_linux() -> Section:
    out = run_command(["lsusb"])
    if out and out.strip():
        return _finalize(_parse_lsusb(out), [])
    # lsusb missing or silent: try the kernel's own USB tree.
    devices = _parse_sysfs_usb()
    if devices:
        return _finalize(devices, ["lsusb unavailable; read /sys/bus/usb (no device names)"])
    return Section(
        "peripherals", _TITLE, Status.UNAVAILABLE, {"usb": []},
        ["no USB devices found (no lsusb and no /sys/bus/usb — common in VMs/WSL2)"],
    )


# --------------------------------------------------------------------------- #
# macOS — system_profiler SPUSBDataType
# --------------------------------------------------------------------------- #

def _parse_macos(out: str) -> List[Dict]:
    """Walk the indented SPUSBDataType tree, pairing each device header with its
    Product ID / Vendor ID / Manufacturer fields.

    A device header is an indented ``Name:`` line with nothing after the colon;
    its attributes follow as ``key: value`` at a deeper indent until the next
    header.
    """
    devices: List[Dict] = []
    current: Optional[Dict] = None
    for raw in out.splitlines():
        line = raw.strip()
        if not line or line == "USB:":
            continue
        if line.endswith(":") and ":" not in line[:-1]:
            current = {"name": line[:-1].strip()}
            devices.append(current)
            continue
        if current is None or ":" not in line:
            continue
        label, _, value = line.partition(":")
        label, value = label.strip(), value.strip()
        if label == "Product ID":
            current["product_id"] = _hex_id(value)
        elif label == "Vendor ID":
            current["vendor_id"] = _hex_id(value)
        elif label == "Manufacturer":
            current["manufacturer"] = value or None
    cleaned = [{k: v for k, v in d.items() if v is not None} for d in devices]
    # Keep only nodes that resolved an actual USB id (drops the bus/hub headers).
    return [d for d in cleaned if d.get("vendor_id") or d.get("product_id")]


def _hex_id(value: str) -> Optional[str]:
    """Normalize a '0x8087' (possibly with a trailing comment) to '8087'."""
    token = value.split()[0] if value else ""
    if token.lower().startswith("0x"):
        token = token[2:]
    token = token.strip()
    return token.lower() if re.fullmatch(r"[0-9a-fA-F]{1,4}", token) else None


def _collect_macos() -> Section:
    out = run_command(["system_profiler", "SPUSBDataType"], timeout=20.0)
    if not out or not out.strip():
        return Section(
            "peripherals", _TITLE, Status.UNAVAILABLE, {"usb": []},
            ["could not enumerate USB via system_profiler"],
        )
    return _finalize(_parse_macos(out), [])


# --------------------------------------------------------------------------- #
# Dispatch
# --------------------------------------------------------------------------- #

@register("peripherals")
def collect() -> Section:
    system = current_os()
    if system == "windows":
        return _collect_windows()
    if system == "linux":
        return _collect_linux()
    if system == "macos":
        return _collect_macos()
    return Section(
        "peripherals", _TITLE, Status.UNSUPPORTED, {"usb": []},
        [f"USB enumeration is not implemented for {system!r} yet"],
    )
