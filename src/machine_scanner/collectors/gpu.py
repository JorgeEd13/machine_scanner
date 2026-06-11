"""GPU collector.

NVIDIA is implemented via ``nvidia-smi`` (present wherever the driver is) — it
doubles as the reference example of the "shell out to an OS tool and parse"
pattern that AMD/Intel and the deeper Windows/Linux probes will follow. When no
NVIDIA GPU is found the section is UNAVAILABLE with a note pointing at the
roadmap, rather than pretending there is no GPU at all.
"""

from __future__ import annotations

import platform

from ..core.models import Section, Status
from ..core.registry import register
from ..core.platform import run_command

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


def _query_nvidia() -> list[dict] | None:
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


@register("gpu")
def collect() -> Section:
    gpus = _query_nvidia()
    if gpus:
        return Section("gpu", "GPU", Status.OK, {"gpus": gpus})

    return Section(
        "gpu",
        "GPU",
        Status.UNAVAILABLE,
        {"gpus": []},
        [
            "no NVIDIA GPU detected via nvidia-smi; "
            "AMD/Intel and integrated-GPU detection are planned (see ROADMAP F2)"
        ],
    )
