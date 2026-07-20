"""Check a machine against the published requirement bars.

:mod:`.fit` answers *"what does this machine run?"*. This answers *"does this
machine clear the bar?"* — the same scan, the other direction, and the one a
buyer reads first.

Two rules carry most of the weight:

**Memory is one requirement with two routes.** A 6 GB graphics card is enough
without 16 GB of RAM; 16 GB of RAM is enough with no card at all. Scoring VRAM
and RAM as independent rows would fail nearly every machine that actually works,
so they are one row that passes if *either* route clears.

**The disk bar moves.** It is the only requirement that depends on what is
already installed: a machine without Ollama and Docker has to fit the model
*and* two installs. Reporting a fixed 5 GB to someone who needs 11 is the kind
of wrong that surfaces after they have paid.
"""

from __future__ import annotations

from typing import Optional

from ..collectors.llm_runtime import install_size_gb
from ..core.models import Inventory
from .catalog import REQUIREMENTS
from .fit import FitProfile

TIERS = ("minimum", "recommended")


class Check:
    """One row of the requirements table."""

    def __init__(
        self,
        key: str,
        label: str,
        actual: Optional[float],
        actual_text: str,
        minimum: float,
        recommended: float,
        unit: str,
        detail: str = "",
    ) -> None:
        self.key = key
        self.label = label
        self.actual = actual
        self.actual_text = actual_text
        self.minimum = minimum
        self.recommended = recommended
        self.unit = unit
        self.detail = detail

    def meets(self, tier: str) -> bool:
        if self.actual is None:
            return False
        return self.actual >= (self.minimum if tier == "minimum" else self.recommended)

    def target_text(self, tier: str) -> str:
        value = self.minimum if tier == "minimum" else self.recommended
        return f"{value:g} {self.unit}".strip()

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "label": self.label,
            "actual": self.actual,
            "actual_text": self.actual_text,
            "minimum": self.minimum,
            "recommended": self.recommended,
            "unit": self.unit,
            "detail": self.detail,
            "meets_minimum": self.meets("minimum"),
            "meets_recommended": self.meets("recommended"),
        }


def disk_requirement(inventory: Inventory, tier: str) -> tuple[float, list[str]]:
    """The free-disk bar, raised by whichever prerequisites are missing.

    Returns ``(gigabytes, reasons)`` — the reasons exist so the report can say
    *why* the number is not the published one, which is the difference between
    a surprising requirement and an explained one.
    """
    base = REQUIREMENTS["disk"].target(tier)
    section = inventory.section("llm_runtime")
    if section is None:
        return base, []

    # Install footprint is OS-dependent (Docker Desktop is a VM stack; the Linux
    # engine is not), so take the OS from the *scan* rather than from whatever
    # machine is rendering it — a saved scan must not be re-costed as this box.
    system = inventory.meta.get("os")

    reasons: list[str] = []
    total = base
    for tool, label in (("ollama", "Ollama"), ("docker", "Docker")):
        info = section.data.get(tool) or {}
        if not info.get("installed"):
            size = install_size_gb(tool, system)
            total += size
            reasons.append(f"+{size:g} GB to install {label}")
    return round(total, 1), reasons


def evaluate(inventory: Inventory, profile: FitProfile) -> tuple[list[Check], list[str]]:
    """Build the requirements table. Returns ``(checks, disk_reasons)``."""
    vram_req = REQUIREMENTS["vram"]
    ram_req = REQUIREMENTS["ram"]
    disk_req = REQUIREMENTS["disk"]
    cores_req = REQUIREMENTS["cores"]

    checks: list[Check] = []

    # --- graphics card ------------------------------------------------------
    # The measured number leads and the card name goes to the detail line: the
    # column is narrow, and truncating "RTX 4050 Laptop GPU - 6 GB" would cut off
    # the only part the decision turns on.
    vram = profile.gpu.vram_gb if profile.accelerated else None
    if profile.accelerated:
        gpu_text = f"{vram:g} GB dedicated"
        gpu_detail = profile.gpu.name or ""
    elif profile.gpu.rejected_name:
        # Naming the card matters: "none detected" reads as a bug to anyone
        # looking at a machine that visibly has one.
        gpu_text = "none usable"
        gpu_detail = (
            f"{profile.gpu.rejected_name} cannot run a model — "
            "optional anyway if there is enough RAM"
        )
    else:
        gpu_text = "none detected"
        gpu_detail = "optional — a machine with enough RAM passes without one"
    checks.append(
        Check(
            "vram", vram_req.label, vram, gpu_text,
            vram_req.minimum, vram_req.recommended, vram_req.unit,
            detail=gpu_detail,
        )
    )

    # --- system RAM ---------------------------------------------------------
    ram = profile.ram_total_gb
    checks.append(
        Check(
            "ram", ram_req.label, ram,
            f"{ram:.1f} GB" if ram is not None else "could not be read",
            ram_req.minimum, ram_req.recommended, ram_req.unit,
        )
    )

    # --- free disk (the moving bar) ----------------------------------------
    disk_min, reasons = disk_requirement(inventory, "minimum")
    disk_rec, _ = disk_requirement(inventory, "recommended")
    free = profile.free_disk_gb
    checks.append(
        Check(
            "disk", disk_req.label, free,
            f"{free:.0f} GB free" if free is not None else "could not be read",
            disk_min, disk_rec, disk_req.unit,
            detail="; ".join(reasons),
        )
    )

    # --- processor ----------------------------------------------------------
    cores = profile.cpu_cores
    checks.append(
        Check(
            "cores", cores_req.label, cores,
            f"{cores} cores" if cores else "could not be read",
            cores_req.minimum, cores_req.recommended, cores_req.unit,
        )
    )

    return checks, reasons


def meets_tier(checks: list[Check], tier: str) -> bool:
    """Whether the machine clears every bar at ``tier``.

    Memory passes by **either** route (see module docstring): the VRAM and RAM
    rows are scored together, not separately.
    """
    memory_ok = any(c.meets(tier) for c in checks if c.key in ("vram", "ram"))
    others_ok = all(c.meets(tier) for c in checks if c.key not in ("vram", "ram"))
    return memory_ok and others_ok


def failing(checks: list[Check], tier: str) -> list[Check]:
    """The rows that block ``tier``, with the memory pair collapsed.

    When neither memory route clears, RAM is reported as the blocker rather than
    both — telling someone their machine fails on two counts when adding RAM
    alone would fix it is discouraging *and* wrong.
    """
    blockers = [c for c in checks if c.key not in ("vram", "ram") and not c.meets(tier)]
    memory = [c for c in checks if c.key in ("vram", "ram")]
    if memory and not any(c.meets(tier) for c in memory):
        blockers.append(next(c for c in memory if c.key == "ram"))
    return blockers
