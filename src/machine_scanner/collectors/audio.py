"""Audio devices collector — sound cards / codecs.

Per-category peripheral collector (ADR-012).

- **Windows** — ``Win32_SoundDevice`` via CIM (name, manufacturer).
- **Linux** — ``/proc/asound/cards`` (ALSA's card registry). No binary, no
  root — preferred over parsing ``aplay -l`` output for the same reason
  ``baseboard`` prefers sysfs (ADR-009).
- **macOS** — ``system_profiler SPAudioDataType``.
- **other** — ``unsupported``.

Never raises: a box with no sound card degrades to ``unavailable``.
"""

from __future__ import annotations

import re

from ..core.models import Section, Status
from ..core.platform import current_os, run_command
from ..core.registry import register
from . import _smbios

_TITLE = "Audio Devices"


def _entry(**fields) -> dict:
    return {key: value for key, value in fields.items() if value is not None}


def _finalize(devices: list[dict], notes: list[str]) -> Section:
    populated = [d for d in devices if d]
    if not populated:
        return Section("audio", _TITLE, Status.UNAVAILABLE, {"devices": []}, notes)
    return Section(
        "audio", _TITLE, Status.OK,
        {"devices": populated, "count": len(populated)}, notes,
    )


# --------------------------------------------------------------------------- #
# Windows — Win32_SoundDevice via CIM
# --------------------------------------------------------------------------- #

_PS_AUDIO = (
    "Get-CimInstance -ClassName Win32_SoundDevice | "
    "Select-Object Name,Manufacturer | ConvertTo-Json -Compress"
)


def _collect_windows() -> Section:
    rows = _smbios.run_cim(_PS_AUDIO)
    if rows is None:
        return Section(
            "audio", _TITLE, Status.UNAVAILABLE, {"devices": []},
            ["could not query audio via CIM (Win32_SoundDevice)"],
        )
    devices = [
        _entry(
            name=_smbios.clean(row.get("Name")),
            manufacturer=_smbios.clean(row.get("Manufacturer")),
        )
        for row in rows
    ]
    return _finalize(devices, [])


# --------------------------------------------------------------------------- #
# Linux — /proc/asound/cards
# --------------------------------------------------------------------------- #

_ASOUND_CARDS = "/proc/asound/cards"
# " 0 [PCH            ]: HDA-Intel - HDA Intel PCH"  ->  index / id / long name
_CARD_RE = re.compile(r"^\s*(\d+)\s*\[([^\]]+)\]\s*:\s*(.*)$")


def _parse_asound(text: str) -> list[dict]:
    devices: list[dict] = []
    for line in text.splitlines():
        match = _CARD_RE.match(line)
        if not match:
            continue  # the second (descriptive) line of each card is ignored
        long_name = match.group(3).strip()
        devices.append(_entry(name=long_name or match.group(2).strip()))
    return devices


def _collect_linux(asound_cards: str = _ASOUND_CARDS) -> Section:
    try:
        with open(asound_cards, errors="replace") as handle:
            text = handle.read()
    except (FileNotFoundError, PermissionError, OSError):
        return Section(
            "audio", _TITLE, Status.UNAVAILABLE, {"devices": []},
            [f"no ALSA card registry at {asound_cards}"],
        )
    if "no soundcards" in text.lower():
        return Section("audio", _TITLE, Status.UNAVAILABLE, {"devices": []},
                       ["ALSA reports no sound cards"])
    return _finalize(_parse_asound(text), [])


# --------------------------------------------------------------------------- #
# macOS — system_profiler SPAudioDataType
# --------------------------------------------------------------------------- #

def _parse_macos(out: str) -> list[dict]:
    """Lift the device headers under SPAudioDataType.

    Entries are indented ``Name:`` headers; the bus/"Devices:" group labels are
    skipped by ignoring known section words.
    """
    skip = {"Audio:", "Devices:"}
    devices: list[dict] = []
    for raw in out.splitlines():
        line = raw.strip()
        if not line or line in skip:
            continue
        if line.endswith(":") and ":" not in line[:-1]:
            devices.append(_entry(name=line[:-1].strip()))
    return devices


def _collect_macos() -> Section:
    out = run_command(["system_profiler", "SPAudioDataType"], timeout=20.0)
    if not out or not out.strip():
        return Section(
            "audio", _TITLE, Status.UNAVAILABLE, {"devices": []},
            ["could not query audio via system_profiler"],
        )
    return _finalize(_parse_macos(out), [])


# --------------------------------------------------------------------------- #
# Dispatch
# --------------------------------------------------------------------------- #

@register("audio")
def collect() -> Section:
    system = current_os()
    if system == "windows":
        return _collect_windows()
    if system == "linux":
        return _collect_linux()
    if system == "macos":
        return _collect_macos()
    return Section(
        "audio", _TITLE, Status.UNSUPPORTED, {"devices": []},
        [f"audio probing is not implemented for {system!r} yet"],
    )
