"""GPU collector — every vendor, not just NVIDIA.

Two layers:

- **General enumeration** lists *all* display adapters per OS — Windows via the
  ``Win32_VideoController`` CIM class, Linux via ``lspci`` (falling back to the
  ``/sys/class/drm`` PCI vendor IDs when ``pciutils`` isn't installed), macOS via
  ``system_profiler SPDisplaysDataType``. This is what brings AMD / Intel /
  integrated GPUs in.
- **NVIDIA enrichment** keeps the ``nvidia-smi`` path: where an NVIDIA driver is
  present it yields live detail (VRAM used, temperature, driver version) that the
  generic enumerators don't, so NVIDIA cards are reported from ``nvidia-smi`` and
  the rest from the OS enumerator. See ADR-010.

A box with no GPU is ``unavailable`` (not an error); an OS we don't enumerate is
``unsupported``. The collector never raises for an expected-absent case.
"""

from __future__ import annotations

import os
import platform
import shlex
from typing import Dict, List, Optional, Tuple

from ..core.models import Section, Status
from ..core.platform import current_os, run_command
from ..core.registry import register
from . import _smbios

# --------------------------------------------------------------------------- #
# NVIDIA — detailed, via nvidia-smi (enrichment layer)
# --------------------------------------------------------------------------- #

# nvidia-smi is on PATH once the driver is installed; on Windows it also lives
# in a couple of well-known locations even when PATH is not set up.
_NVIDIA_SMI_CANDIDATES = ["nvidia-smi"]
if platform.system() == "Windows":
    _NVIDIA_SMI_CANDIDATES += [
        r"C:\Windows\System32\nvidia-smi.exe",
        r"C:\Program Files\NVIDIA Corporation\NVSMI\nvidia-smi.exe",
    ]

_QUERY = "--query-gpu=name,memory.total,memory.used,driver_version,temperature.gpu"
_FORMAT = "--format=csv,noheader,nounits"
_FIELDS = ["name", "memory_total_mb", "memory_used_mb", "driver_version", "temperature_c"]


def _query_nvidia() -> Optional[List[Dict]]:
    for cmd in _NVIDIA_SMI_CANDIDATES:
        out = run_command([cmd, _QUERY, _FORMAT])
        if not out:
            continue
        gpus = []
        for line in out.strip().splitlines():
            parts = [p.strip() for p in line.split(",")]
            if len(parts) != len(_FIELDS):
                continue
            entry = dict(zip(_FIELDS, parts))
            # numeric fields come back as bare strings — coerce when possible
            for key in ("memory_total_mb", "memory_used_mb", "temperature_c"):
                try:
                    entry[key] = float(entry[key])
                except (ValueError, TypeError):
                    pass
            entry["vendor"] = "NVIDIA"
            gpus.append(entry)
        return gpus or None
    return None


# --------------------------------------------------------------------------- #
# vendor / unit helpers
# --------------------------------------------------------------------------- #

def _classify_vendor(text: object) -> Optional[str]:
    """Normalize a free-form vendor/name string to NVIDIA / AMD / Intel."""
    cleaned = _smbios.clean(text)
    if cleaned is None:
        return None
    low = cleaned.lower()
    if "nvidia" in low:
        return "NVIDIA"
    if "intel" in low:
        return "Intel"
    if any(tag in low for tag in ("amd", "ati", "advanced micro", "radeon")):
        return "AMD"
    return cleaned


# PCI vendor IDs (hex, lower-case, no 0x) for the sysfs fallback.
_PCI_VENDORS = {"10de": "NVIDIA", "1002": "AMD", "1022": "AMD", "8086": "Intel"}


def _mb_from_text(text: str) -> Optional[float]:
    """Parse a '1536 MB' / '2 GB' VRAM string into megabytes."""
    parts = text.strip().split()
    if not parts:
        return None
    try:
        value = float(parts[0])
    except ValueError:
        return None
    unit = parts[1].lower() if len(parts) > 1 else "mb"
    if unit.startswith("g"):
        value *= 1024
    return round(value)


def _entry(vendor, name, **extra) -> Dict:
    """Build a GPU record, dropping empty fields so the output stays clean."""
    rec: Dict = {}
    if vendor is not None:
        rec["vendor"] = vendor
    if name is not None:
        rec["name"] = name
    for key, value in extra.items():
        if value is not None:
            rec[key] = value
    return rec


# --------------------------------------------------------------------------- #
# Windows — Win32_VideoController via CIM
# --------------------------------------------------------------------------- #

_PS_GPU = (
    "Get-CimInstance -ClassName Win32_VideoController | "
    "Select-Object Name,AdapterCompatibility,AdapterRAM,DriverVersion,VideoProcessor | "
    "ConvertTo-Json -Compress"
)


def _enumerate_windows() -> Tuple[Optional[List[Dict]], List[str]]:
    rows = _smbios.run_cim(_PS_GPU)
    if rows is None:
        return None, ["could not enumerate display adapters via CIM (Win32_VideoController)"]
    notes: List[str] = []
    gpus: List[Dict] = []
    capped = False
    for row in rows:
        name = _smbios.clean(row.get("Name"))
        vendor = _classify_vendor(row.get("AdapterCompatibility")) or _classify_vendor(name)
        mem_mb = None
        ram = row.get("AdapterRAM")
        if isinstance(ram, (int, float)) and ram > 0:
            mem_mb = round(ram / (1024 * 1024))
            capped = capped or ram >= 4 * 1024 ** 3 - 1
        gpus.append(
            _entry(
                vendor,
                name,
                memory_total_mb=mem_mb,
                driver_version=_smbios.clean(row.get("DriverVersion")),
            )
        )
    if capped:
        notes.append(
            "AdapterRAM is a 32-bit WMI field and saturates at 4 GiB; VRAM may be "
            "under-reported for larger cards"
        )
    return gpus, notes


# --------------------------------------------------------------------------- #
# Linux — lspci, falling back to /sys/class/drm PCI vendor IDs
# --------------------------------------------------------------------------- #

_DRM_DIR = "/sys/class/drm"
_GPU_PCI_CLASSES = ("vga compatible controller", "3d controller", "display controller")


def _parse_lspci(out: str) -> List[Dict]:
    gpus: List[Dict] = []
    for line in out.strip().splitlines():
        try:
            fields = shlex.split(line)
        except ValueError:
            continue
        # lspci -mm: <slot> "<class>" "<vendor>" "<device>" ...
        if len(fields) < 4 or fields[1].lower() not in _GPU_PCI_CLASSES:
            continue
        gpus.append(
            _entry(_classify_vendor(fields[2]) or _smbios.clean(fields[2]), _smbios.clean(fields[3]))
        )
    return gpus


def _enumerate_linux(drm_dir: str = _DRM_DIR) -> Tuple[Optional[List[Dict]], List[str]]:
    out = run_command(["lspci", "-mm"])
    if out:
        return _parse_lspci(out), []

    # Fallback: classify by PCI vendor id from sysfs (no pciutils needed, no name).
    if not os.path.isdir(drm_dir):
        return None, ["could not enumerate GPUs (no lspci and no /sys/class/drm)"]
    gpus: List[Dict] = []
    for entry in sorted(os.listdir(drm_dir)):
        # real cards are card0, card1, … (skip connector nodes like card0-eDP-1)
        if not (entry.startswith("card") and entry[4:].isdigit()):
            continue
        vendor_path = os.path.join(drm_dir, entry, "device", "vendor")
        try:
            with open(vendor_path, "r", errors="replace") as handle:
                vid = handle.read().strip().lower().removeprefix("0x")
        except OSError:
            continue
        gpus.append(_entry(_PCI_VENDORS.get(vid, f"PCI {vid}"), None))
    note = "lspci (pciutils) not found; reporting PCI vendor only — install it for adapter names"
    return gpus, [note]


# --------------------------------------------------------------------------- #
# macOS — system_profiler SPDisplaysDataType
# --------------------------------------------------------------------------- #

def _parse_macos(out: str) -> List[Dict]:
    gpus: List[Dict] = []
    current: Optional[Dict] = None
    for raw in out.splitlines():
        line = raw.strip()
        if line.startswith("Chipset Model:"):
            current = _entry(None, _smbios.clean(line.split(":", 1)[1]))
            gpus.append(current)
        elif current is None:
            continue
        elif line.startswith("Vendor:"):
            current["vendor"] = _classify_vendor(line.split(":", 1)[1]) or current.get("vendor")
        elif line.startswith("VRAM"):
            mem = _mb_from_text(line.split(":", 1)[1])
            if mem is not None:
                current["memory_total_mb"] = mem
    return gpus


def _enumerate_macos() -> Tuple[Optional[List[Dict]], List[str]]:
    out = run_command(["system_profiler", "SPDisplaysDataType"], timeout=20.0)
    if not out or not out.strip():
        return None, ["could not enumerate GPUs via system_profiler"]
    return _parse_macos(out), []


# --------------------------------------------------------------------------- #
# Dispatch + merge
# --------------------------------------------------------------------------- #

def _enumerate(system: str) -> Tuple[Optional[List[Dict]], List[str]]:
    if system == "windows":
        return _enumerate_windows()
    if system == "linux":
        return _enumerate_linux()
    if system == "macos":
        return _enumerate_macos()
    return None, []


@register("gpu")
def collect() -> Section:
    system = current_os()
    general, notes = _enumerate(system)
    nvidia = _query_nvidia()

    if general is None and nvidia is None:
        if system not in ("windows", "linux", "macos"):
            return Section(
                "gpu", "GPU", Status.UNSUPPORTED, {"gpus": []},
                [f"GPU enumeration is not implemented for {system!r}"],
            )
        return Section(
            "gpu", "GPU", Status.UNAVAILABLE, {"gpus": []},
            notes or ["no GPU detected"],
        )

    # NVIDIA cards come from nvidia-smi (richer); everything else from the
    # generic enumerator. If nvidia-smi is absent, keep the enumerator's NVIDIA
    # rows so the card still shows up, just without the live detail.
    gpus: List[Dict] = []
    if general is not None:
        for gpu in general:
            if gpu.get("vendor") == "NVIDIA" and nvidia:
                continue
            gpus.append(gpu)
    if nvidia:
        gpus.extend(nvidia)

    if not gpus:
        return Section("gpu", "GPU", Status.UNAVAILABLE, {"gpus": []}, notes or ["no GPU detected"])
    return Section("gpu", "GPU", Status.OK, {"gpus": gpus}, notes)
