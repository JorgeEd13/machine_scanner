"""Physical storage drives collector — the real disks behind the partitions.

Distinct from the ``disk`` collector (which is the psutil partitions / usage
view): this one reaches *past* psutil into the physical drives — model, serial,
firmware, capacity, **bus type** (NVMe / SATA / USB) and **media type**
(SSD / HDD), plus **SMART health** where readable. It is the deep-hardware layer
``disk`` is missing, and follows the same per-OS judgement as ADR-009/010/013.

- **Windows** — ``MSFT_PhysicalDisk`` (``root\\microsoft\\windows\\storage``)
  is the spine: it exposes ``MediaType`` (SSD/HDD) and ``BusType`` (NVMe/SATA/
  USB) cleanly *and* a storage-stack ``HealthStatus`` — none of which
  ``Win32_DiskDrive`` gives without guesswork. ``Win32_DiskDrive`` is the
  fallback for older builds (model/serial/firmware/size, coarse bus, no media).
  The raw SMART predictive-failure bit (``MSStorageDriver_FailurePredictStatus``,
  ``root\\wmi``) needs administrator, so it degrades to PARTIAL + an elevation
  note when blocked. See ADR-013.
- **Linux** — ``lsblk -d -b -O -J`` (it emits JSON — we parse that, not
  columns): model / serial / firmware (``rev``) / size / ``rota`` (HDD vs SSD) /
  ``tran`` (bus). ``/sys/block/*`` is the no-``lsblk`` fallback. SMART via
  ``smartctl`` needs root → degrade + note when absent.
- **macOS** — ``diskutil info -all`` (media name / size / protocol / SSD flag).
- **other** — ``unsupported``.

Never raises for an expected-absent / locked-down case (no readable drive, no
SMART without root) — it degrades to UNAVAILABLE / PARTIAL with an accurate note.
"""

from __future__ import annotations

import json
import os

from ..core.models import Section, Status
from ..core.platform import current_os, is_admin, run_command
from ..core.registry import register
from . import _smbios

_NAME = "storage_devices"
_TITLE = "Storage Drives"

_GB = 1024 ** 3


def _entry(**fields) -> dict:
    """Build a drive record, dropping empty fields."""
    return {key: value for key, value in fields.items() if value is not None}


def _bytes_to_gb(value: object) -> float | None:
    """Coerce a byte count (int, float, or digit string) to GB."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and value > 0:
        return round(value / _GB, 2)
    if isinstance(value, str) and value.strip().isdigit():
        size = int(value)
        return round(size / _GB, 2) if size > 0 else None
    return None


def _finalize(drives: list[dict], notes: list[str], *, smart_gated: bool = False) -> Section:
    """Decide the section status from what was collected.

    - no readable physical drive at all            -> UNAVAILABLE
    - drives present but SMART was privilege-gated  -> PARTIAL + elevation note
      (the baseboard / memory_modules root-gating pattern)
    - everything else                               -> OK
    """
    populated = [d for d in drives if d]
    if not populated:
        return Section(_NAME, _TITLE, Status.UNAVAILABLE, {"drives": []}, notes)
    data = {"drives": populated, "count": len(populated)}
    total = sum(d.get("size_gb", 0) or 0 for d in populated)
    if total:
        data["total_gb"] = round(total, 2)
    status = Status.PARTIAL if smart_gated else Status.OK
    return Section(_NAME, _TITLE, status, data, notes)


# --------------------------------------------------------------------------- #
# Windows — MSFT_PhysicalDisk (+ Win32_DiskDrive fallback, SMART best-effort)
# --------------------------------------------------------------------------- #

# MSFT_PhysicalDisk.MediaType -> label (0 unspecified, 3 HDD, 4 SSD, 5 SCM).
_WIN_MEDIA = {3: "HDD", 4: "SSD", 5: "SCM"}

# MSFT_PhysicalDisk.BusType -> label (the documented subset).
_WIN_BUS = {
    1: "SCSI", 2: "ATAPI", 3: "ATA", 4: "1394", 5: "SSA", 6: "Fibre Channel",
    7: "USB", 8: "RAID", 9: "iSCSI", 10: "SAS", 11: "SATA", 12: "SD",
    13: "MMC", 14: "Virtual", 15: "File Backed Virtual", 16: "Storage Spaces",
    17: "NVMe", 18: "SCM", 19: "UFS",
}

# MSFT_PhysicalDisk.HealthStatus -> label (0 healthy, 1 warning, 2 unhealthy).
_WIN_HEALTH = {0: "healthy", 1: "warning", 2: "unhealthy"}

_PS_PHYSICAL = (
    "Get-CimInstance -Namespace root\\microsoft\\windows\\storage "
    "-ClassName MSFT_PhysicalDisk | Select-Object "
    "DeviceId,FriendlyName,Model,SerialNumber,FirmwareVersion,"
    "MediaType,BusType,Size,HealthStatus,SpindleSpeed | ConvertTo-Json -Compress"
)

# Predictive-failure (the raw SMART bit). Wrapped in @() so a readable-but-empty
# result is "[]" rather than nothing, telling "no rows" apart from "blocked".
_PS_SMART = (
    "$r = @(Get-CimInstance -Namespace root\\wmi "
    "-ClassName MSStorageDriver_FailurePredictStatus -ErrorAction SilentlyContinue | "
    "Select-Object InstanceName,PredictFailure); "
    "ConvertTo-Json -InputObject $r -Compress"
)

_PS_DISKDRIVE = (
    "Get-CimInstance -ClassName Win32_DiskDrive | Select-Object "
    "Model,SerialNumber,FirmwareRevision,Size,InterfaceType | ConvertTo-Json -Compress"
)


def _label_from_code(value: object, table: dict[int, str]) -> str | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return table.get(int(value))


def _drive_from_msft(row: dict) -> dict:
    spindle = row.get("SpindleSpeed")
    return _entry(
        model=_smbios.clean(row.get("Model")) or _smbios.clean(row.get("FriendlyName")),
        serial=_smbios.clean(row.get("SerialNumber")),
        firmware=_smbios.clean(row.get("FirmwareVersion")),
        size_gb=_bytes_to_gb(row.get("Size")),
        bus=_label_from_code(row.get("BusType"), _WIN_BUS),
        media=_label_from_code(row.get("MediaType"), _WIN_MEDIA),
        health=_label_from_code(row.get("HealthStatus"), _WIN_HEALTH),
        # SpindleSpeed is 0 on SSDs and a real RPM on spinning disks.
        rpm=int(spindle) if isinstance(spindle, (int, float)) and spindle > 0 else None,
    )


def _drive_from_win32(row: dict) -> dict:
    return _entry(
        model=_smbios.clean(row.get("Model")),
        serial=_smbios.clean(row.get("SerialNumber")),
        firmware=_smbios.clean(row.get("FirmwareRevision")),
        size_gb=_bytes_to_gb(row.get("Size")),
        # InterfaceType is coarse (IDE / SCSI / USB / 1394) — no NVMe, no media.
        bus=_smbios.clean(row.get("InterfaceType")),
    )


def _smart_predicts_failure(smart_rows: list[dict]) -> bool | None:
    """Reduce the predictive-failure rows to a single 'any drive failing?' bool.

    We deliberately do *not* try to map each predictive-failure row back to a
    physical disk — ``InstanceName`` is a SCSI port path that does not carry the
    disk number, so per-drive correlation would be guesswork. The honest signal
    is the fleet-wide "is any drive predicting failure", attached as a section
    note; per-drive ``health`` already comes from MSFT_PhysicalDisk.
    """
    flags = [bool(r.get("PredictFailure")) for r in smart_rows]
    if not flags:
        return None
    return any(flags)


def _collect_windows() -> Section:
    rows = _smbios.run_cim(_PS_PHYSICAL)
    drives: list[dict] = []
    notes: list[str] = []
    if rows:
        drives = [_drive_from_msft(r) for r in rows]
    else:
        # Older Windows without the storage WMI provider — fall back.
        fallback = _smbios.run_cim(_PS_DISKDRIVE)
        if fallback is None:
            return Section(
                _NAME, _TITLE, Status.UNAVAILABLE, {"drives": []},
                ["could not query physical disks via CIM "
                 "(MSFT_PhysicalDisk / Win32_DiskDrive)"],
            )
        drives = [_drive_from_win32(r) for r in fallback]
        notes.append(
            "MSFT_PhysicalDisk unavailable; used Win32_DiskDrive "
            "(no media type, coarse bus type)"
        )

    # SMART predictive-failure bit (best effort; needs administrator).
    smart_rows = _smbios.run_cim(_PS_SMART)
    smart_gated = False
    if smart_rows is None:
        smart_gated = not is_admin()
        notes.append(
            "SMART predictive-failure status (MSStorageDriver_FailurePredictStatus) "
            "needs administrator; reporting storage-stack health only"
            if smart_gated else
            "SMART predictive-failure status was not readable"
        )
    else:
        failing = _smart_predicts_failure(smart_rows)
        if failing is True:
            notes.append("SMART predicts imminent failure on at least one drive")
        elif failing is False:
            notes.append("SMART: no imminent failure predicted")

    return _finalize(drives, notes, smart_gated=smart_gated)


# --------------------------------------------------------------------------- #
# Linux — lsblk -d -b -O -J (sysfs fallback), smartctl for health
# --------------------------------------------------------------------------- #

# lsblk "tran" (transport) -> bus label.
_LINUX_TRAN = {
    "nvme": "NVMe", "sata": "SATA", "ata": "ATA", "usb": "USB", "sas": "SAS",
    "scsi": "SCSI", "mmc": "MMC", "virtio": "VirtIO", "spi": "SPI", "iscsi": "iSCSI",
}

# Block-device name prefixes that are not physical drives.
_LINUX_SKIP = ("loop", "ram", "sr", "dm-", "md", "zram", "fd", "nbd")


def _bus_label(tran: object) -> str | None:
    if not tran:
        return None
    text = str(tran).strip().lower()
    return _LINUX_TRAN.get(text, text.upper() or None)


def _media_from_rota(rota: object) -> str | None:
    text = str(rota).strip()
    if text in ("1", "True"):
        return "HDD"
    if text in ("0", "False"):
        return "SSD"
    return None


def _drive_from_lsblk(dev: dict) -> dict:
    return _entry(
        name=_smbios.clean(dev.get("name")),
        model=_smbios.clean(dev.get("model")),
        serial=_smbios.clean(dev.get("serial")),
        firmware=_smbios.clean(dev.get("rev")),
        size_gb=_bytes_to_gb(dev.get("size")),
        bus=_bus_label(dev.get("tran")),
        media=_media_from_rota(dev.get("rota")),
    )


def _parse_lsblk(raw: str) -> list[dict]:
    obj = json.loads(raw)
    devices = obj.get("blockdevices") or []
    drives: list[dict] = []
    for dev in devices:
        if dev.get("type") not in (None, "disk"):
            continue
        name = str(dev.get("name") or "")
        if name.startswith(_LINUX_SKIP):
            continue
        drives.append(_drive_from_lsblk(dev))
    return [d for d in drives if d]


_SYS_BLOCK = "/sys/block"


def _read_sysfs(path: str) -> str | None:
    try:
        with open(path, errors="replace") as handle:
            return handle.read().strip() or None
    except (FileNotFoundError, PermissionError, OSError):
        return None


def _drive_from_sysfs(block_root: str, name: str) -> dict:
    base = os.path.join(block_root, name)
    dev = os.path.join(base, "device")
    sectors = _read_sysfs(os.path.join(base, "size"))
    size_gb = None
    if sectors and sectors.isdigit():
        # /sys/block/<dev>/size is in 512-byte sectors regardless of real LBA.
        size_gb = _bytes_to_gb(int(sectors) * 512)
    return _entry(
        name=name,
        model=_smbios.clean(_read_sysfs(os.path.join(dev, "model"))),
        serial=_smbios.clean(_read_sysfs(os.path.join(dev, "serial"))),
        firmware=_smbios.clean(
            _read_sysfs(os.path.join(dev, "rev"))
            or _read_sysfs(os.path.join(dev, "firmware_rev"))
        ),
        size_gb=size_gb,
        # sysfs is bus-poor: only the NVMe naming is unambiguous without lspci.
        bus="NVMe" if name.startswith("nvme") else None,
        media=_media_from_rota(_read_sysfs(os.path.join(base, "queue", "rotational"))),
    )


def _collect_linux_sysfs(block_root: str = _SYS_BLOCK) -> list[dict]:
    if not os.path.isdir(block_root):
        return []
    drives: list[dict] = []
    for name in sorted(os.listdir(block_root)):
        if name.startswith(_LINUX_SKIP):
            continue
        drives.append(_drive_from_sysfs(block_root, name))
    return [d for d in drives if d]


def _smart_health_linux(name: str) -> str | None:
    """Return 'passed' / 'failed' from ``smartctl -H -j``; None if unreadable."""
    out = run_command(["smartctl", "-H", "-j", "/dev/" + name])
    if not out or not out.strip():
        return None
    try:
        passed = json.loads(out).get("smart_status", {}).get("passed")
    except (ValueError, TypeError, AttributeError):
        return None
    if passed is None:
        return None
    return "passed" if passed else "failed"


def _collect_linux() -> Section:
    raw = run_command(["lsblk", "-d", "-b", "-O", "-J"])
    notes: list[str] = []
    if raw and raw.strip():
        try:
            drives = _parse_lsblk(raw)
        except (ValueError, TypeError):
            drives = []
    else:
        drives = _collect_linux_sysfs(_SYS_BLOCK)
        if drives:
            notes.append("lsblk unavailable; read /sys/block (bus type names are limited)")

    if not drives:
        return Section(
            _NAME, _TITLE, Status.UNAVAILABLE, {"drives": []},
            ["no physical drives found via lsblk or /sys/block "
             "(common in containers / VMs without block devices)"],
        )

    # SMART health via smartctl (needs root). Best effort: if the first probe is
    # unreadable, stop hammering and degrade with one note.
    smart_gated = False
    smart_unreadable = False
    for drive in drives:
        name = drive.get("name")
        if not name:
            continue
        health = _smart_health_linux(name)
        if health is None:
            smart_unreadable = True
            break
        drive["health"] = health
    if smart_unreadable:
        smart_gated = not is_admin()
        notes.append(
            "SMART health needs smartctl and root; run as root with "
            "smartmontools installed for drive health"
            if smart_gated else
            "SMART health unavailable (smartctl not installed?)"
        )

    return _finalize(drives, notes, smart_gated=smart_gated)


# --------------------------------------------------------------------------- #
# macOS — diskutil info -all
# --------------------------------------------------------------------------- #

# diskutil label -> (our key, transform). Only physical drives are kept.
_MAC_FIELDS = {
    "Device / Media Name": "model",
    "Disk Size": "size_gb",
    "Protocol": "bus",
    "SMART Status": "health",
}


def _mac_size_to_gb(text: str) -> float | None:
    """diskutil reports e.g. '500.3 GB (500277790720 Bytes)' — prefer the bytes."""
    if "(" in text and "Bytes" in text:
        inner = text[text.index("(") + 1 : text.index("Bytes")].replace(",", "").strip()
        if inner.isdigit():
            return _bytes_to_gb(int(inner))
    return None


def _parse_diskutil(out: str) -> list[dict]:
    """Parse ``diskutil info -all`` text — blocks split by a row of '****'.

    Only *physical* drives are kept: a block is emitted when it is explicitly
    ``Virtual: No`` (the disk-image / synthesized volumes are ``Virtual: Yes``
    and dropped). The separator ends the current block; a block accumulates from
    its first field, so we seed ``current`` before the loop and flush at the end.
    """
    drives: list[dict] = []
    current: dict = {}
    is_physical = False

    def flush() -> None:
        if is_physical:
            drives.append({k: v for k, v in current.items() if not k.startswith("_")})

    for raw in out.splitlines():
        line = raw.strip()
        if line and set(line) == {"*"}:  # block separator
            flush()
            current, is_physical = {}, False
            continue
        if ":" not in line:
            continue
        label, _, value = line.partition(":")
        label, value = label.strip(), value.strip()
        if label == "Virtual":
            is_physical = value.lower() == "no"
        if label == "Solid State":
            current["media"] = "SSD" if value.lower() == "yes" else "HDD"
        key = _MAC_FIELDS.get(label)
        if key == "size_gb":
            size = _mac_size_to_gb(value)
            if size is not None:
                current["size_gb"] = size
        elif key:
            cleaned = _smbios.clean(value)
            if cleaned:
                current[key] = cleaned
    flush()
    return [d for d in drives if d]


def _collect_macos() -> Section:
    out = run_command(["diskutil", "info", "-all"], timeout=20.0)
    if not out or not out.strip():
        return Section(
            _NAME, _TITLE, Status.UNAVAILABLE, {"drives": []},
            ["could not query drives via diskutil"],
        )
    return _finalize(_parse_diskutil(out), [])


# --------------------------------------------------------------------------- #
# Dispatch
# --------------------------------------------------------------------------- #

@register(_NAME)
def collect() -> Section:
    system = current_os()
    if system == "windows":
        return _collect_windows()
    if system == "linux":
        return _collect_linux()
    if system == "macos":
        return _collect_macos()
    return Section(
        _NAME, _TITLE, Status.UNSUPPORTED, {"drives": []},
        [f"physical storage probing is not implemented for {system!r} yet"],
    )
