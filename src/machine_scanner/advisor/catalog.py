"""Model catalog — public Ollama chat models and what each one costs to run.

Three numbers per model, and they answer three different questions:

* ``ram_gb`` / ``vram_gb`` — memory needed to *run* it, on CPU or on GPU. GPU
  needs slightly more than CPU for the same model because the KV cache and the
  CUDA context live in VRAM alongside the weights, with no swap to fall back on.
* ``disk_gb`` — approximate **download** size of the default (Q4-ish) tag. A box
  with the RAM but not the disk is a different failure, and a caller that only
  checks memory reports "fits" for a model the machine cannot even pull.
* ``quality`` — a coarse 1–10 capability rank used only to *order* the catalog.
  It is a judgement call, not a benchmark, and the tiers below are deliberately
  wide enough that small disagreements do not change the recommendation.

All figures are approximate and describe the default quantized tags as
published by Ollama; they are the sizing rule of thumb, not a guarantee. Real
memory use moves with context length and quantization.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelSpec:
    """A local chat model and the resources it needs to run comfortably."""

    name: str            # Ollama tag
    ram_gb: float        # approx. RAM needed to run on CPU
    vram_gb: float       # approx. VRAM needed to run on GPU
    disk_gb: float       # approx. download size of the default tag
    quality: int         # coarse 1-10 capability rank (higher = better)
    description: str
    licence: str = "Apache-2.0"   # the terms the USER inherits by running it
    commercial: bool = True       # may a business run it in the ordinary course?

    def memory_required(self, accelerated: bool) -> float:
        """Memory this model needs, given whether a usable GPU is present."""
        return self.vram_gb if accelerated else self.ram_gb


# Ordered by quality, tiny -> strong. The floor is a model that runs on almost
# anything; the ceiling needs a workstation and is here mainly so a strong box
# is told it is strong rather than silently capped at the mid tier.
# ⚠️ A model being free to download does NOT mean it is free to use at work.
# Open *weights* are not open *source*: some are released under research or
# community licences that restrict commercial use or attach conditions. The
# `licence`/`commercial` fields exist so this tool never headlines a model that
# somebody would then run in their business without knowing.
#
# `qwen2.5:3b` is the trap that prompted this: every other Qwen2.5 size here is
# Apache-2.0, and the 3B is not — and it happens to be the highest-quality model
# that fits a modest 4 GB machine, so it was the one most likely to be picked.
CATALOG = (
    ModelSpec("qwen2.5:0.5b", 1.0, 1.5, 0.4, 1, "Absolute floor — runs almost anywhere"),
    ModelSpec("qwen2.5:1.5b", 1.5, 2.0, 1.0, 2, "Tiny but tool-capable — small footprint"),
    ModelSpec("llama3.2:3b", 3.0, 4.0, 2.0, 4, "Balanced — good for ~8 GB RAM, no GPU",
              licence="Llama Community License"),
    ModelSpec("qwen2.5:3b", 3.0, 4.0, 1.9, 5, "Balanced, but research-licensed — not for business use",
              licence="Qwen Research License", commercial=False),
    ModelSpec("qwen2.5:7b", 5.0, 6.0, 4.7, 7, "Good quality — needs ~6 GB VRAM or ~10 GB RAM"),
    ModelSpec("llama3.1:8b", 6.0, 7.0, 4.9, 7, "Alternative to qwen2.5:7b",
              licence="Llama Community License"),
    ModelSpec("gemma2:9b", 7.0, 8.0, 5.4, 8, "High quality — needs ~12 GB RAM",
              licence="Gemma Terms of Use"),
    ModelSpec("qwen2.5:14b", 9.0, 10.0, 9.0, 9, "Very high quality — needs ~16 GB VRAM"),
    ModelSpec("llama3.3:70b", 42.0, 45.0, 43.0, 10, "Excellent — high-end GPU or 64 GB+ RAM",
              licence="Llama Community License"),
)


# Capability bands, keyed by the quality rank of the best model that fits.
# Deliberately about *what the machine can run*, not about whether any given
# workload is a good idea on it — that judgement belongs to the caller.
_BANDS = (
    (7, "comfortable", "Runs a good-quality local model comfortably."),
    (3, "workable", "Runs a small local model. Usable, noticeably slower and weaker."),
    (1, "minimal", "Only the tiniest models fit. Expect short, shallow answers."),
)

NO_FIT_BAND = "unusable"
NO_FIT_SUMMARY = "No model in the catalog fits this machine's usable memory."


# --------------------------------------------------------------------------- #
# Published requirement tiers
# --------------------------------------------------------------------------- #
#
# The catalog above answers "what does *this* machine run?". These answer the
# other half — "what does a machine need?" — and they are **fixed on purpose**.
#
# A threshold derived from the machine being measured can never be failed: every
# box meets its own minimum by construction, and the no-go case loses its
# reference point. So these are published bars, in the shape a buyer already
# understands from game system requirements: check your machine against the
# column, and the verdict tells you where you land.
#
# `minimum` is the weakest configuration still worth running — the 3B class.
# Below it only 0.5-1.5B models fit, and those are confidently wrong often
# enough that "it technically runs" is not a useful answer.
# `recommended` is the 7B class, where answers stop being a compromise.


class Requirement:
    """One published bar: what a component needs, and how to say it."""

    def __init__(self, label: str, minimum: float, recommended: float, unit: str = "GB") -> None:
        self.label = label
        self.minimum = minimum
        self.recommended = recommended
        self.unit = unit

    def target(self, tier: str) -> float:
        return self.minimum if tier == "minimum" else self.recommended

    def format(self, value: float) -> str:
        return f"{value:g} {self.unit}".strip()


# RAM is sold in standard sizes, and a machine NEVER reports its sticker figure:
# firmware, integrated graphics and reserved regions take a slice first. An 8 GB
# box reports ~7.9, and a 16 GB box with an Intel iGPU can report ~14.6. Comparing
# the reported number against a bar of 8 or 16 therefore rejects exactly the
# machines the bar was written to admit — found on a real Windows 8 GB box
# (2026-07-20), which read NO when it should have read YES, WITH LIMITS.
_STANDARD_RAM_GB = (2, 4, 6, 8, 12, 16, 24, 32, 48, 64, 96, 128, 192, 256)

# How far below its sticker size a machine may report and still be credited with
# it. 12% covers the worst case seen (a 16 GB laptop reserving ~9% for its iGPU)
# without reaching the next size down.
_RAM_REPORTING_SLACK = 0.88


def nominal_ram_gb(reported: float) -> float:
    """The size this machine was sold as, inferred from what it reports.

    Rounds up to the nearest standard size only when the reported figure is
    close enough to be that size minus its reserved slice; otherwise the
    reported number is returned unchanged, so an unusual configuration is never
    credited with memory it does not have.
    """
    for size in _STANDARD_RAM_GB:
        if size * _RAM_REPORTING_SLACK <= reported <= size:
            return float(size)
    return reported


# Memory is expressed two ways because the same model needs different amounts
# depending on where it runs: system RAM is shared with the OS (hence the 80%
# rule), dedicated VRAM is not.
REQUIREMENTS = {
    "vram": Requirement("Graphics card", 4.0, 8.0),
    "ram": Requirement("Memory (RAM)", 8.0, 16.0),
    "disk": Requirement("Free disk", 5.0, 10.0),
    "cores": Requirement("Processor", 4, 8, unit="cores"),
}

# A machine clears the memory bar by EITHER route — a 6 GB graphics card is
# enough without 16 GB of RAM, and 16 GB of RAM is enough with no card at all.
# Treating them as two independent requirements would fail almost every machine
# that actually works.
MEMORY_ROUTES = ("vram", "ram")



def band_for(quality: int | None) -> tuple[str, str]:
    """Map the best fitting model's quality rank to ``(band, summary)``."""
    if quality is None:
        return NO_FIT_BAND, NO_FIT_SUMMARY
    for threshold, name, summary in _BANDS:
        if quality >= threshold:
            return name, summary
    return NO_FIT_BAND, NO_FIT_SUMMARY
