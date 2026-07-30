"""Monitors / displays collector — the attached screens and their EDID identity.

Per-category peripheral collector (ADR-012). Each connected display advertises
an **EDID** block carrying its manufacturer (a 3-letter PnP ID), product code,
serial number and model name. The three OSes expose that differently:

- **Windows** — ``WmiMonitorID`` in the ``root\\wmi`` namespace via CIM. It
  pre-decodes the EDID strings into ``uint16`` char-code arrays (so no raw EDID
  bit-twiddling is needed here).
- **Linux** — the kernel exposes the **raw EDID blob** per connector at
  ``/sys/class/drm/*/edid``; we parse it directly (``_parse_edid``). No root,
  no binary — same "sysfs when it's strictly better" judgement as ADR-009.
- **macOS** — ``system_profiler SPDisplaysDataType`` (displays nested under the
  GPU); we lift the display names and resolutions.
- **other** — ``unsupported``.

Never raises: a headless box / disconnected connector degrades to
``unavailable`` with a note.
"""

from __future__ import annotations

import os

from ..core.models import Section, Status
from ..core.platform import current_os, run_command
from ..core.registry import register
from . import _smbios

_TITLE = "Monitors / Displays"


def _entry(**fields) -> dict:
    return {key: value for key, value in fields.items() if value is not None}


def _finalize(monitors: list[dict], notes: list[str]) -> Section:
    populated = [m for m in monitors if m]
    if not populated:
        return Section("monitors", _TITLE, Status.UNAVAILABLE, {"monitors": []}, notes)
    return Section(
        "monitors", _TITLE, Status.OK,
        {"monitors": populated, "count": len(populated)}, notes,
    )


# --------------------------------------------------------------------------- #
# EDID parsing (shared by the Linux sysfs path; reusable + unit-tested)
# --------------------------------------------------------------------------- #

_EDID_HEADER = b"\x00\xff\xff\xff\xff\xff\xff\x00"


def _decode_manufacturer(b0: int, b1: int) -> str | None:
    """Bytes 8-9 pack three 5-bit letters (1=A) big-endian into the PnP ID."""
    packed = (b0 << 8) | b1
    letters = [(packed >> 10) & 0x1F, (packed >> 5) & 0x1F, packed & 0x1F]
    if any(code < 1 or code > 26 for code in letters):
        return None
    return "".join(chr(code + ord("A") - 1) for code in letters)


def _descriptor_text(block: bytes) -> str:
    """An EDID display-descriptor string runs to a 0x0A terminator, space-padded."""
    text = block.decode("latin-1")
    return text.split("\n", 1)[0].strip()


def _parse_edid(blob: bytes) -> dict | None:
    """Parse the fixed EDID 1.x fields we care about from a 128-byte block."""
    if len(blob) < 128 or blob[:8] != _EDID_HEADER:
        return None
    manufacturer = _decode_manufacturer(blob[8], blob[9])
    product_code = blob[10] | (blob[11] << 8)          # little-endian
    serial_num = int.from_bytes(blob[12:16], "little")
    name: str | None = None
    serial_str: str | None = None
    # Four 18-byte descriptors at 54/72/90/108; a display descriptor starts with
    # 00 00 00 and a type tag at byte 3 (0xFC = name, 0xFF = serial string).
    for offset in (54, 72, 90, 108):
        block = blob[offset:offset + 18]
        if len(block) < 18 or block[0] != 0 or block[1] != 0 or block[2] != 0:
            continue
        tag, payload = block[3], block[5:18]
        if tag == 0xFC:
            name = _descriptor_text(payload) or name
        elif tag == 0xFF:
            serial_str = _descriptor_text(payload) or serial_str
    return _entry(
        name=name,
        manufacturer=manufacturer,
        product_code=f"{product_code:04X}" if product_code else None,
        serial=serial_str or (str(serial_num) if serial_num else None),
    )


# --------------------------------------------------------------------------- #
# Windows — WmiMonitorID (root\wmi) via CIM
# --------------------------------------------------------------------------- #

_PS_MON = (
    "Get-CimInstance -Namespace root\\wmi -ClassName WmiMonitorID "
    "-ErrorAction SilentlyContinue | "
    "Select-Object ManufacturerName,ProductCodeID,SerialNumberID,UserFriendlyName | "
    "ConvertTo-Json -Compress"
)


def _decode_charcodes(value: object) -> str | None:
    """WmiMonitorID string fields are null-terminated uint16 char-code arrays."""
    if not isinstance(value, list):
        return None
    chars = [chr(c) for c in value if isinstance(c, int) and 0 < c < 0x110000]
    return "".join(chars).strip() or None


def _collect_windows() -> Section:
    rows = _smbios.run_cim(_PS_MON)
    if rows is None:
        return Section(
            "monitors", _TITLE, Status.UNAVAILABLE, {"monitors": []},
            ["could not query displays via CIM (WmiMonitorID, root\\wmi)"],
        )
    monitors = [
        _entry(
            name=_decode_charcodes(row.get("UserFriendlyName")),
            manufacturer=_decode_charcodes(row.get("ManufacturerName")),
            product_code=_decode_charcodes(row.get("ProductCodeID")),
            serial=_decode_charcodes(row.get("SerialNumberID")),
        )
        for row in rows
    ]
    return _finalize(monitors, [])


# --------------------------------------------------------------------------- #
# Linux — /sys/class/drm/*/edid (raw EDID blob)
# --------------------------------------------------------------------------- #

_DRM_DIR = "/sys/class/drm"


def _collect_linux(drm_dir: str = _DRM_DIR) -> Section:
    if not os.path.isdir(drm_dir):
        return Section(
            "monitors", _TITLE, Status.UNAVAILABLE, {"monitors": []},
            [f"no DRM connectors at {drm_dir} (common on headless VMs / WSL2)"],
        )
    monitors: list[dict] = []
    for name in sorted(os.listdir(drm_dir)):
        edid_path = os.path.join(drm_dir, name, "edid")
        try:
            with open(edid_path, "rb") as handle:
                blob = handle.read()
        except (FileNotFoundError, PermissionError, OSError):
            continue
        if not blob:  # connector present but nothing plugged in
            continue
        parsed = _parse_edid(blob)
        if parsed:
            # strip the "card0-" prefix from e.g. "card0-HDMI-A-1"
            parsed["connector"] = name.split("-", 1)[1] if "-" in name else name
            monitors.append(parsed)
    if not monitors:
        return Section(
            "monitors", _TITLE, Status.UNAVAILABLE, {"monitors": []},
            ["no connected displays with readable EDID"],
        )
    return _finalize(monitors, [])


# --------------------------------------------------------------------------- #
# macOS — system_profiler SPDisplaysDataType
# --------------------------------------------------------------------------- #

def _parse_macos(out: str) -> list[dict]:
    """Lift display entries from SPDisplaysDataType (displays nest under the GPU).

    A display header is an indented ``Name:`` line; ``Resolution`` follows.
    """
    monitors: list[dict] = []
    current: dict | None = None
    for raw in out.splitlines():
        line = raw.strip()
        if not line or line == "Graphics/Displays:":
            continue
        if line.endswith(":") and ":" not in line[:-1]:
            current = {"name": line[:-1].strip()}
            continue
        if current is None or ":" not in line:
            continue
        label, _, value = line.partition(":")
        if label.strip() == "Resolution":
            current["resolution"] = value.strip() or None
            monitors.append(current)
            current = None
    return [{k: v for k, v in m.items() if v is not None} for m in monitors]


def _collect_macos() -> Section:
    out = run_command(["system_profiler", "SPDisplaysDataType"], timeout=20.0)
    if not out or not out.strip():
        return Section(
            "monitors", _TITLE, Status.UNAVAILABLE, {"monitors": []},
            ["could not query displays via system_profiler"],
        )
    return _finalize(_parse_macos(out), [])


# --------------------------------------------------------------------------- #
# Dispatch
# --------------------------------------------------------------------------- #

@register("monitors")
def collect() -> Section:
    system = current_os()
    if system == "windows":
        return _collect_windows()
    if system == "linux":
        return _collect_linux()
    if system == "macos":
        return _collect_macos()
    return Section(
        "monitors", _TITLE, Status.UNSUPPORTED, {"monitors": []},
        [f"display enumeration is not implemented for {system!r} yet"],
    )
