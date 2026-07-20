"""Which local LLM fits this machine — derived from a completed scan.

The heuristic in one line: **usable memory decides**, and usable memory is VRAM
on a box with a GPU that can actually accelerate inference, otherwise ~80% of
system RAM. The 20% headroom is not decoration — a model sized to *total* RAM
loads and then thrashes, because the OS, the desktop and the process holding the
model all need to stay resident.

Three things the naive version of this gets wrong, and why the code is longer
than the one line above:

1. **Not every GPU is an accelerator.** An Intel integrated GPU has no VRAM of
   its own — it borrows system RAM — so counting its reported memory *and* the
   RAM double-counts the same gigabytes and recommends a model that will not
   load. Integrated GPUs are therefore excluded and the machine is sized on the
   CPU path.
2. **Not every VRAM number is trustworthy.** ``nvidia-smi`` reports the real
   figure. Windows' ``AdapterRAM`` is a 32-bit field that saturates at 4 GiB, so
   a 12 GB card reads as 4 GB there — the answer degrades (a too-small
   recommendation, never a too-large one) and says so in a note.
3. **Memory is not the only limit.** A model that fits in RAM but not on disk
   cannot be pulled at all, so the disk check is part of the verdict rather than
   a footnote after it.

Everything here is pure: an :class:`Inventory` in, a :class:`Section` out. No
subprocess, no probing, and consequently tests that make no assumption about
the machine they run on.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from ..core.models import Inventory, Section, Status
from .catalog import CATALOG, band_for

ADVISOR_NAME = "ollama_fit"
ADVISOR_TITLE = "Local LLM Fit"

# Fraction of system RAM assumed available to a model on the CPU path.
_RAM_HEADROOM = 0.80

# Below this, a reported GPU memory figure is noise (a stub adapter, a rounding
# artifact) rather than a pool a model could live in.
_MIN_USEFUL_VRAM_GB = 1.0

# Windows' Win32_VideoController.AdapterRAM is a 32-bit field: anything at or
# just under 4 GiB may be a saturated reading of a larger card.
_ADAPTER_RAM_CAP_GB = 4.0

# Names that mean "this GPU shares system RAM", regardless of vendor.
_INTEGRATED_MARKERS = (
    "integrated",
    "uhd graphics",
    "hd graphics",
    "iris",
    "vega 3",
    "vega 6",
    "vega 7",
    "vega 8",
    "vega 11",
    "radeon graphics",
    "radeon(tm) graphics",
    "apple m",
)


def _rows(section: Section | None, key: str) -> list[dict]:
    """The list of records under ``data[key]``, or ``[]`` if absent/malformed."""
    if section is None:
        return []
    value = section.data.get(key)
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    return [row for row in value if isinstance(row, Mapping)]


def _number(value: Any) -> float | None:
    """Coerce a scan field to a float, tolerating the strings some probes emit."""
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _is_integrated(name: str | None, vendor: str | None) -> bool:
    """True when the adapter shares system RAM instead of owning VRAM."""
    text = f"{vendor or ''} {name or ''}".lower()
    if any(marker in text for marker in _INTEGRATED_MARKERS):
        return True
    # Intel's only discrete line is Arc; everything else Intel ships is an iGPU.
    return "intel" in text and "arc" not in text


class GpuVerdict:
    """Whether a GPU can accelerate inference here, and how much VRAM it offers."""

    def __init__(
        self,
        accelerated: bool,
        vram_gb: float | None,
        name: str | None,
        notes: list[str],
        rejected_name: str | None = None,
    ) -> None:
        self.accelerated = accelerated
        self.vram_gb = vram_gb
        self.name = name
        self.notes = notes
        # A card that exists but cannot be used. Kept because "none detected" is
        # a lie to anyone looking at a machine that visibly has a graphics chip,
        # and "your card is integrated" is the answer they need.
        self.rejected_name = rejected_name


def _pick_gpu(gpus: list[dict]) -> GpuVerdict:
    """Choose the adapter that would actually run the model, if any.

    Picks the discrete GPU with the most usable VRAM. A machine with an
    integrated *and* a discrete GPU — every gaming laptop — must be sized on the
    discrete one, so integrated adapters are filtered out before the comparison
    rather than merely losing it.
    """
    notes: list[str] = []
    best: dict | None = None
    best_vram = 0.0
    saw_integrated = False
    integrated_name: str | None = None

    for gpu in gpus:
        name = gpu.get("name")
        vendor = gpu.get("vendor")
        if _is_integrated(name, vendor):
            saw_integrated = True
            integrated_name = integrated_name or name or vendor
            continue
        mb = _number(gpu.get("memory_total_mb"))
        if mb is None:
            continue
        vram = round(mb / 1024, 1)
        if vram > best_vram:
            best, best_vram = gpu, vram

    if best is None or best_vram <= _MIN_USEFUL_VRAM_GB:
        if saw_integrated:
            notes.append(
                "integrated GPU ignored — it shares system RAM rather than "
                "owning VRAM, so sizing uses the CPU path"
            )
        if best is not None:
            notes.append(
                f"discrete GPU reports only {best_vram:.1f} GB — too little to "
                "hold a model, sizing uses the CPU path"
            )
        rejected = (best or {}).get("name") or integrated_name
        return GpuVerdict(False, None, None, notes, rejected_name=rejected)

    name = best.get("name")
    vendor = str(best.get("vendor") or "").upper()

    # nvidia-smi rows carry a driver_version; a row without one came from the OS
    # enumerator, where the VRAM figure is the unreliable 32-bit field.
    if "driver_version" not in best and best_vram >= _ADAPTER_RAM_CAP_GB - 0.1:
        notes.append(
            f"VRAM read as {best_vram:.1f} GB from the OS adapter table, which "
            "saturates at 4 GB — a larger card is under-reported and the "
            "recommendation is conservative"
        )
    if vendor and "NVIDIA" not in vendor:
        notes.append(
            f"{vendor} GPU acceleration depends on the driver stack being "
            "present and supported; if it is not, the CPU path applies instead"
        )

    return GpuVerdict(True, best_vram, name, notes)


class FitProfile:
    """The four numbers model selection actually turns on."""

    def __init__(
        self,
        ram_total_gb: float | None,
        gpu: GpuVerdict,
        cpu_cores: int | None,
        free_disk_gb: float | None,
    ) -> None:
        self.ram_total_gb = ram_total_gb
        self.gpu = gpu
        self.cpu_cores = cpu_cores
        self.free_disk_gb = free_disk_gb

    @property
    def accelerated(self) -> bool:
        return self.gpu.accelerated

    @property
    def usable_memory_gb(self) -> float | None:
        """VRAM on an accelerated box, else ~80% of system RAM."""
        if self.accelerated and self.gpu.vram_gb is not None:
            return self.gpu.vram_gb
        if self.ram_total_gb is None:
            return None
        return round(self.ram_total_gb * _RAM_HEADROOM, 1)

    @property
    def memory_basis(self) -> str:
        return "GPU VRAM" if self.accelerated else f"{int(_RAM_HEADROOM * 100)}% of system RAM"


def extract_profile(inventory: Inventory) -> FitProfile:
    """Read the sizing inputs out of a completed scan. Never raises."""
    memory = inventory.section("memory")
    ram_total = _number(memory.data.get("total_gb")) if memory else None

    cpu = inventory.section("cpu")
    cores = _number(cpu.data.get("cores_logical")) if cpu else None

    gpu = _pick_gpu(_rows(inventory.section("gpu"), "gpus"))

    # Ollama's model directory is configurable, so which partition it lands on is
    # unknowable from a scan. The most free space anywhere is the honest upper
    # bound: it never promises room the machine does not have.
    free = [
        value
        for value in (_number(part.get("free_gb")) for part in _rows(inventory.section("disk"), "partitions"))
        if value is not None
    ]

    return FitProfile(
        ram_total_gb=ram_total,
        gpu=gpu,
        cpu_cores=int(cores) if cores else None,
        free_disk_gb=max(free) if free else None,
    )


def recommend(profile: FitProfile) -> tuple[dict | None, list[dict]]:
    """Rank the catalog against this machine.

    Returns ``(best, rows)``. ``best`` is the highest-quality model that fits
    both memory and disk, or ``None`` when nothing does. Each row is
    ``{name, quality, description, memory_required_gb, disk_required_gb,
    fits_memory, fits_disk, fits}``.
    """
    usable = profile.usable_memory_gb
    free_disk = profile.free_disk_gb

    rows: list[dict] = []
    for spec in CATALOG:
        required = spec.memory_required(profile.accelerated)
        fits_memory = usable is not None and usable >= required
        # Unknown free space must not veto a model — an absent disk section is
        # missing information, not evidence of a full disk.
        fits_disk = free_disk is None or free_disk >= spec.disk_gb
        rows.append(
            {
                "name": spec.name,
                "quality": spec.quality,
                "description": spec.description,
                "memory_required_gb": required,
                "disk_required_gb": spec.disk_gb,
                "fits_memory": fits_memory,
                "fits_disk": fits_disk,
                "fits": fits_memory and fits_disk,
            }
        )

    best = max(
        (row for row in rows if row["fits"]),
        key=lambda row: row["quality"],
        default=None,
    )
    return best, rows


def _verdict_notes(profile: FitProfile, best: dict | None, rows: list[dict]) -> list[str]:
    """Caveats that change how the verdict should be read."""
    notes = list(profile.gpu.notes)

    # Only reachable on the GPU path — on the CPU path an unknown RAM figure
    # leaves nothing to size with and the section is UNAVAILABLE before here.
    if profile.ram_total_gb is None:
        notes.append("system RAM could not be read — sized on VRAM alone")

    # Disk, not memory, is the binding constraint: worth saying out loud, because
    # it is the one a client can fix in ten minutes.
    if best is None and any(row["fits_memory"] for row in rows):
        notes.append(
            "this machine has the memory for a model but not the free disk space "
            "to download one — freeing space changes the verdict"
        )
    elif best is not None:
        blocked = [row for row in rows if row["fits_memory"] and not row["fits_disk"]]
        if blocked:
            notes.append(
                f"{len(blocked)} larger model(s) fit in memory but not in the "
                f"{profile.free_disk_gb:.0f} GB of free disk space found"
            )

    # Core count only matters where the CPU does the work.
    if not profile.accelerated and profile.cpu_cores is not None and profile.cpu_cores < 4:
        notes.append(
            f"{profile.cpu_cores} logical cores on the CPU path — expect slow "
            "generation even where a model fits"
        )
    return notes


def build_section(inventory: Inventory) -> Section:
    """Derive the ``ollama_fit`` section from a completed scan.

    Degrades like a collector: a scan with no memory *and* no GPU information
    (``--only network``, or psutil absent) yields ``UNAVAILABLE`` with the reason,
    never a guess.
    """
    profile = extract_profile(inventory)

    if profile.usable_memory_gb is None:
        return Section(
            ADVISOR_NAME,
            ADVISOR_TITLE,
            Status.UNAVAILABLE,
            {},
            ["needs the memory or gpu section to size a model; neither was collected"],
        )

    best, rows = recommend(profile)
    band, summary = band_for(best["quality"] if best else None)
    notes = _verdict_notes(profile, best, rows)

    data: dict = {
        "verdict": band,
        "summary": summary,
        "recommended_model": best["name"] if best else None,
        "usable_memory_gb": profile.usable_memory_gb,
        "memory_basis": profile.memory_basis,
        "gpu_accelerated": profile.accelerated,
        "gpu_name": profile.gpu.name,
        "free_disk_gb": profile.free_disk_gb,
        "cpu_cores_logical": profile.cpu_cores,
        "models": rows,
    }

    # An unusable verdict is a real answer about the machine, not a scan failure:
    # PARTIAL would imply the advisor could not finish, which is not what happened.
    status = Status.OK if profile.ram_total_gb is not None else Status.PARTIAL
    return Section(ADVISOR_NAME, ADVISOR_TITLE, status, data, notes)


def append_to(inventory: Inventory, only: list[str] | None = None) -> Inventory:
    """Append the advisor section to a scan, honouring an ``--only`` filter.

    Mutates and returns ``inventory`` so the CLI can chain it onto ``run_all``.
    """
    if only is not None and ADVISOR_NAME not in only:
        return inventory
    inventory.sections.append(build_section(inventory))
    return inventory
