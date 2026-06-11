"""Motherboard / BIOS / serial-number collector — the first probe that goes
*beyond* psutil into firmware-level identity (SMBIOS / DMI).

This is the reference implementation of the per-OS "deep hardware" pattern:

- **Windows** — CIM (``Get-CimInstance``) via PowerShell, *not* the deprecated
  ``wmic`` (removed from recent Windows builds). See ADR-009.
- **Linux** — the kernel-exported DMI table under ``/sys/class/dmi/id/``. No
  ``dmidecode`` binary and no root needed for the identity fields; only the
  serial / UUID files are root-readable, so their absence becomes a privilege
  note rather than a failure. See ADR-009.
- **macOS** — ``system_profiler SPHardwareDataType`` via ``run_command``.
- **anything else** — an honest ``UNSUPPORTED`` section.

Firmware tables are notoriously full of placeholder junk ("To Be Filled By
O.E.M.", "Default string", …); ``_clean`` drops those so a blank field reads as
genuinely unknown instead of as vendor boilerplate. The collector never raises
for an expected-absent case — a locked-down serial or a missing DMI table
degrades to PARTIAL / UNAVAILABLE with a note.
"""

from __future__ import annotations

import json
import os
from typing import Dict, Optional

from ..core.models import Section, Status
from ..core.platform import current_os, is_admin, run_command
from ..core.registry import register

_TITLE = "Motherboard / BIOS"

# Serial / UUID fields are the ones that typically require elevation; we track
# them separately so we can attach a precise "run elevated for more" note.
_SERIAL_FIELDS = ("system_serial", "system_uuid", "baseboard_serial", "bios_serial")

# Common SMBIOS placeholder strings (lower-cased) that mean "not really set".
_PLACEHOLDERS = {
    "",
    "to be filled by o.e.m.",
    "to be filled by o.e.m",
    "default string",
    "none",
    "not specified",
    "not available",
    "not applicable",
    "no enclosure",
    "system serial number",
    "system manufacturer",
    "system product name",
    "system version",
    "base board version",
    "base board serial number",
    "base board asset tag",
    "chassis serial number",
    "0",
    "00000000",
    "unknown",
    "n/a",
    "fffffffffffffffffffffff",
    "ffffffff-ffff-ffff-ffff-ffffffffffff",
}


def _clean(value: object) -> Optional[str]:
    """Strip a SMBIOS string and reduce vendor placeholders to ``None``."""
    if value is None:
        return None
    text = str(value).strip()
    if text.lower() in _PLACEHOLDERS:
        return None
    return text or None


def _finalize(
    data: Dict[str, Optional[str]],
    notes: list,
    *,
    elevated: bool,
) -> Section:
    """Decide the section status from what was actually collected.

    - nothing identifying at all                       -> UNAVAILABLE
    - identity present but *no* serial/UUID readable
      while not elevated (a systematic privilege block) -> PARTIAL + note
    - everything else (a single blank serial field is
      just empty firmware, not a privilege problem)     -> OK
    """
    present = {k: v for k, v in data.items() if v is not None}
    if not present:
        return Section(
            "baseboard",
            _TITLE,
            Status.UNAVAILABLE,
            {},
            notes + ["no motherboard / BIOS identity could be read"],
        )

    any_serial = any(data.get(f) is not None for f in _SERIAL_FIELDS)
    missing_serials = [f for f in _SERIAL_FIELDS if data.get(f) is None]
    status = Status.OK
    if missing_serials and not any_serial and not elevated:
        # We got identity but not a single serial/UUID and we are unprivileged:
        # that pattern means elevation is gating them, so say so.
        status = Status.PARTIAL
        notes.append(
            "serial numbers / UUID were not readable without elevation; "
            "run as administrator (Windows) or root (Linux) for the full set"
        )

    return Section("baseboard", _TITLE, status, present, notes)


# --------------------------------------------------------------------------- #
# Windows — CIM via PowerShell (ADR-009)
# --------------------------------------------------------------------------- #

# One PowerShell pass over the three SMBIOS-backed CIM classes, emitted as a
# single compact JSON object. ReleaseDate is a CIM DateTime; we format it to an
# ISO date so it survives JSON cleanly (PS 5.1 would otherwise emit /Date(ms)/).
_PS_SCRIPT = r"""
$ErrorActionPreference = 'SilentlyContinue'
$bios  = Get-CimInstance -ClassName Win32_BIOS
$board = Get-CimInstance -ClassName Win32_BaseBoard
$sys   = Get-CimInstance -ClassName Win32_ComputerSystemProduct
$date  = if ($bios.ReleaseDate) { $bios.ReleaseDate.ToString('yyyy-MM-dd') } else { $null }
[pscustomobject]@{
    bios_vendor            = $bios.Manufacturer
    bios_version           = $bios.SMBIOSBIOSVersion
    bios_release_date      = $date
    bios_serial            = $bios.SerialNumber
    baseboard_manufacturer = $board.Manufacturer
    baseboard_product      = $board.Product
    baseboard_version      = $board.Version
    baseboard_serial       = $board.SerialNumber
    system_manufacturer    = $sys.Vendor
    system_product         = $sys.Name
    system_version         = $sys.Version
    system_serial          = $sys.IdentifyingNumber
    system_uuid            = $sys.UUID
} | ConvertTo-Json -Compress
"""


def _parse_windows(raw: str) -> Dict[str, Optional[str]]:
    """Parse the PowerShell JSON blob into the normalized, cleaned field set."""
    obj = json.loads(raw)
    return {key: _clean(value) for key, value in obj.items()}


def _collect_windows() -> Section:
    # PowerShell start-up plus three CIM queries can exceed the default 5s on a
    # slow box, so give this probe a more generous budget.
    raw = run_command(
        [
            "powershell",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            _PS_SCRIPT,
        ],
        timeout=20.0,
    )
    if not raw or not raw.strip():
        return Section(
            "baseboard",
            _TITLE,
            Status.UNAVAILABLE,
            {},
            ["could not query SMBIOS via PowerShell CIM (Get-CimInstance)"],
        )
    try:
        data = _parse_windows(raw)
    except (ValueError, TypeError):
        return Section(
            "baseboard",
            _TITLE,
            Status.UNAVAILABLE,
            {},
            ["unexpected output from PowerShell CIM query"],
        )
    return _finalize(data, [], elevated=is_admin())


# --------------------------------------------------------------------------- #
# Linux — kernel DMI table under /sys/class/dmi/id (ADR-009)
# --------------------------------------------------------------------------- #

_DMI_DIR = "/sys/class/dmi/id"

# sysfs file name -> normalized field name.
_DMI_MAP = {
    "sys_vendor": "system_manufacturer",
    "product_name": "system_product",
    "product_version": "system_version",
    "product_serial": "system_serial",
    "product_uuid": "system_uuid",
    "board_vendor": "baseboard_manufacturer",
    "board_name": "baseboard_product",
    "board_version": "baseboard_version",
    "board_serial": "baseboard_serial",
    "bios_vendor": "bios_vendor",
    "bios_version": "bios_version",
    "bios_date": "bios_release_date",
}


def _collect_linux(dmi_dir: str = _DMI_DIR) -> Section:
    if not os.path.isdir(dmi_dir):
        return Section(
            "baseboard",
            _TITLE,
            Status.UNAVAILABLE,
            {},
            [f"no DMI table exposed at {dmi_dir} (common on VMs / containers)"],
        )

    data: Dict[str, Optional[str]] = {field: None for field in _DMI_MAP.values()}
    blocked_by_privilege = False
    for filename, field in _DMI_MAP.items():
        path = os.path.join(dmi_dir, filename)
        try:
            with open(path, "r", errors="replace") as handle:
                data[field] = _clean(handle.read())
        except PermissionError:
            # serial / uuid files are mode 0400 (root only) — expected.
            blocked_by_privilege = True
        except (FileNotFoundError, OSError):
            pass

    # On Linux the privilege signal is the unreadable file itself, so treat a
    # permission-blocked read the same as "not elevated" for the note.
    return _finalize(data, [], elevated=is_admin() and not blocked_by_privilege)


# --------------------------------------------------------------------------- #
# macOS — system_profiler via run_command
# --------------------------------------------------------------------------- #

# "Profiler label" -> normalized field. system_profiler exposes system-level
# identity; it does not surface separate BIOS/baseboard rows, so those stay None.
_MAC_MAP = {
    "Model Name": "system_product",
    "Model Identifier": "system_version",
    "Manufacturer": "system_manufacturer",
    "Serial Number (system)": "system_serial",
    "Hardware UUID": "system_uuid",
    "Boot ROM Version": "bios_version",
}


def _parse_macos(raw: str) -> Dict[str, Optional[str]]:
    data: Dict[str, Optional[str]] = {}
    for line in raw.splitlines():
        if ":" not in line:
            continue
        label, _, value = line.partition(":")
        field = _MAC_MAP.get(label.strip())
        if field is not None:
            data[field] = _clean(value)
    # Apple machines are all Apple-made; system_profiler omits a vendor row.
    data.setdefault("system_manufacturer", "Apple")
    return data


def _collect_macos() -> Section:
    raw = run_command(["system_profiler", "SPHardwareDataType"], timeout=20.0)
    if not raw or not raw.strip():
        return Section(
            "baseboard",
            _TITLE,
            Status.UNAVAILABLE,
            {},
            ["could not query hardware via system_profiler"],
        )
    return _finalize(_parse_macos(raw), [], elevated=is_admin())


# --------------------------------------------------------------------------- #
# Dispatch
# --------------------------------------------------------------------------- #

@register("baseboard")
def collect() -> Section:
    system = current_os()
    if system == "windows":
        return _collect_windows()
    if system == "linux":
        return _collect_linux()
    if system == "macos":
        return _collect_macos()
    return Section(
        "baseboard",
        _TITLE,
        Status.UNSUPPORTED,
        {},
        [f"motherboard / BIOS probing is not implemented for {system!r} yet"],
    )
