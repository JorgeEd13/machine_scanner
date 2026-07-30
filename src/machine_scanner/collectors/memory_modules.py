"""Physical memory modules collector — the DIMMs in the slots, per stick.

Distinct from the ``memory`` collector (which reports total / used RAM via
psutil): this one reaches into SMBIOS for the *physical* modules — slot, size,
speed, type (DDR4/DDR5/…), manufacturer and part number.

- **Windows** — ``Win32_PhysicalMemory`` via CIM.
- **Linux** — ``dmidecode -t memory``. SMBIOS type 17 has **no unprivileged
  sysfs equivalent**, so this genuinely needs root; without it we degrade to
  ``unavailable`` with an elevation note rather than failing. (This is the
  inverse of ``baseboard``, where sysfs let us avoid ``dmidecode`` — see
  ADR-009 / ADR-010.)
- **macOS** — ``system_profiler SPMemoryDataType`` (per-DIMM on Intel Macs;
  Apple-Silicon unified memory reports as a single entry with no slot).
- **other** — ``unsupported``.

Never raises for an expected-absent case (empty slot, locked-down DMI table).
"""

from __future__ import annotations

from ..core.models import Section, Status
from ..core.platform import current_os, is_admin, run_command
from ..core.registry import register
from . import _smbios

_TITLE = "Memory Modules"

# SMBIOS "Memory Device" type codes (SMBIOSMemoryType on Windows) -> label.
_DDR_TYPES = {
    20: "DDR",
    21: "DDR2",
    24: "DDR3",
    26: "DDR4",
    27: "LPDDR",
    28: "LPDDR2",
    29: "LPDDR3",
    30: "LPDDR4",
    34: "DDR5",
    35: "LPDDR5",
}


def _entry(**fields) -> dict:
    """Build a module record, dropping empty fields."""
    return {key: value for key, value in fields.items() if value is not None}


def _finalize(modules: list[dict], notes: list[str]) -> Section:
    populated = [m for m in modules if m]
    if not populated:
        return Section("memory_modules", _TITLE, Status.UNAVAILABLE, {"modules": []}, notes)
    data = {"modules": populated, "count": len(populated)}
    total = sum(m.get("capacity_gb", 0) or 0 for m in populated)
    if total:
        data["total_gb"] = round(total, 1)
    return Section("memory_modules", _TITLE, Status.OK, data, notes)


# --------------------------------------------------------------------------- #
# Windows — Win32_PhysicalMemory via CIM
# --------------------------------------------------------------------------- #

_PS_MEM = (
    "Get-CimInstance -ClassName Win32_PhysicalMemory | "
    "Select-Object DeviceLocator,BankLabel,Capacity,Speed,ConfiguredClockSpeed,"
    "Manufacturer,PartNumber,SMBIOSMemoryType | ConvertTo-Json -Compress"
)


def _type_label(code: object) -> str | None:
    if isinstance(code, bool) or not isinstance(code, (int, float)):
        return None
    code = int(code)
    if code in (0, 1, 2):  # 0 unknown / 1 other / 2 unknown-ish
        return None
    return _DDR_TYPES.get(code, f"type {code}")


def _collect_windows() -> Section:
    rows = _smbios.run_cim(_PS_MEM)
    if rows is None:
        return Section(
            "memory_modules", _TITLE, Status.UNAVAILABLE, {"modules": []},
            ["could not query memory modules via CIM (Win32_PhysicalMemory)"],
        )
    modules: list[dict] = []
    for row in rows:
        capacity = row.get("Capacity")
        cap_gb = None
        if isinstance(capacity, (int, float)) and capacity > 0:
            cap_gb = round(capacity / (1024 ** 3), 1)
        elif isinstance(capacity, str) and capacity.isdigit():
            cap_gb = round(int(capacity) / (1024 ** 3), 1)
        speed = row.get("ConfiguredClockSpeed") or row.get("Speed")
        modules.append(
            _entry(
                slot=_smbios.clean(row.get("DeviceLocator")) or _smbios.clean(row.get("BankLabel")),
                capacity_gb=cap_gb,
                speed_mhz=speed if isinstance(speed, (int, float)) and speed > 0 else None,
                type=_type_label(row.get("SMBIOSMemoryType")),
                manufacturer=_smbios.clean(row.get("Manufacturer")),
                part_number=_smbios.clean(row.get("PartNumber")),
            )
        )
    return _finalize(modules, [])


# --------------------------------------------------------------------------- #
# Linux — dmidecode -t memory (needs root)
# --------------------------------------------------------------------------- #

# dmidecode field label -> our normalized key (value parsed further below).
_DMIDECODE_FIELDS = {
    "Locator": "slot",
    "Size": "capacity_gb",
    "Speed": "speed_mhz",
    "Configured Memory Speed": "speed_mhz",
    "Type": "type",
    "Manufacturer": "manufacturer",
    "Part Number": "part_number",
}


def _parse_dmidecode(out: str) -> list[dict]:
    modules: list[dict] = []
    current: dict | None = None
    for raw in out.splitlines():
        if raw.startswith("Memory Device"):
            current = {}
            modules.append(current)
            continue
        if current is None or ":" not in raw:
            continue
        label, _, value = raw.strip().partition(":")
        key = _DMIDECODE_FIELDS.get(label.strip())
        if key is None:
            continue
        value = value.strip()
        if key == "capacity_gb":
            current[key] = _size_to_gb(value)
        elif key == "speed_mhz":
            current[key] = _speed_to_mhz(value) or current.get("speed_mhz")
        else:
            current[key] = _smbios.clean(value)
    # Drop slots with no module installed (Size "No Module Installed" -> None).
    return [{k: v for k, v in m.items() if v is not None} for m in modules if m.get("capacity_gb")]


def _size_to_gb(text: str) -> float | None:
    parts = text.split()
    if len(parts) < 2 or not parts[0].replace(".", "", 1).isdigit():
        return None
    value = float(parts[0])
    unit = parts[1].lower()
    if unit.startswith(("mb", "mib")):
        value /= 1024
    elif unit.startswith(("tb", "tib")):
        value *= 1024
    return round(value, 1)


def _speed_to_mhz(text: str) -> int | None:
    parts = text.split()
    if not parts or not parts[0].isdigit():
        return None
    return int(parts[0])


def _collect_linux() -> Section:
    out = run_command(["dmidecode", "-t", "memory"])
    if not out or not out.strip():
        note = "memory modules need root via dmidecode (SMBIOS type 17 has no unprivileged sysfs); run as root"
        return Section("memory_modules", _TITLE, Status.UNAVAILABLE, {"modules": []}, [note])
    notes: list[str] = []
    if not is_admin():
        notes.append("dmidecode usually requires root; results may be incomplete")
    return _finalize(_parse_dmidecode(out), notes)


# --------------------------------------------------------------------------- #
# macOS — system_profiler SPMemoryDataType
# --------------------------------------------------------------------------- #

_MAC_FIELDS = {
    "Size": "capacity_gb",
    "Type": "type",
    "Speed": "speed_mhz",
    "Manufacturer": "manufacturer",
    "Part Number": "part_number",
}


def _parse_macos(out: str) -> list[dict]:
    modules: list[dict] = []
    current: dict | None = None
    for raw in out.splitlines():
        line = raw.strip()
        # A slot header looks like "BANK 0/DIMM0:" or "DIMM0:" with nothing after.
        if line.endswith(":") and ("DIMM" in line or "BANK" in line):
            current = {"slot": line[:-1].strip()}
            modules.append(current)
            continue
        if current is None or ":" not in line:
            continue
        label, _, value = line.partition(":")
        key = _MAC_FIELDS.get(label.strip())
        if key is None:
            continue
        value = value.strip()
        if key == "capacity_gb":
            current[key] = _size_to_gb(value)
        elif key == "speed_mhz":
            current[key] = _speed_to_mhz(value)
        else:
            current[key] = _smbios.clean(value)
    cleaned = [{k: v for k, v in m.items() if v is not None} for m in modules]
    return [m for m in cleaned if m.get("capacity_gb")]


def _collect_macos() -> Section:
    out = run_command(["system_profiler", "SPMemoryDataType"], timeout=20.0)
    if not out or not out.strip():
        return Section(
            "memory_modules", _TITLE, Status.UNAVAILABLE, {"modules": []},
            ["could not query memory via system_profiler"],
        )
    modules = _parse_macos(out)
    notes = []
    if not modules:
        # Apple Silicon: unified memory, no discrete slots.
        notes.append("no per-slot memory reported (Apple-Silicon unified memory has no DIMM slots)")
    return _finalize(modules, notes)


# --------------------------------------------------------------------------- #
# Dispatch
# --------------------------------------------------------------------------- #

@register("memory_modules")
def collect() -> Section:
    system = current_os()
    if system == "windows":
        return _collect_windows()
    if system == "linux":
        return _collect_linux()
    if system == "macos":
        return _collect_macos()
    return Section(
        "memory_modules", _TITLE, Status.UNSUPPORTED, {"modules": []},
        [f"physical memory module probing is not implemented for {system!r} yet"],
    )
