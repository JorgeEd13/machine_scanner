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

    def memory_required(self, accelerated: bool) -> float:
        """Memory this model needs, given whether a usable GPU is present."""
        return self.vram_gb if accelerated else self.ram_gb


# Ordered by quality, tiny -> strong. The floor is a model that runs on almost
# anything; the ceiling needs a workstation and is here mainly so a strong box
# is told it is strong rather than silently capped at the mid tier.
CATALOG = (
    ModelSpec("qwen2.5:0.5b", 1.0, 1.5, 0.4, 1, "Absolute floor — runs almost anywhere"),
    ModelSpec("qwen2.5:1.5b", 1.5, 2.0, 1.0, 2, "Tiny but tool-capable — small footprint"),
    ModelSpec("llama3.2:3b", 3.0, 4.0, 2.0, 4, "Balanced — good for ~8 GB RAM, no GPU"),
    ModelSpec("qwen2.5:3b", 3.0, 4.0, 1.9, 5, "Balanced — solid tool-calling at 3B"),
    ModelSpec("qwen2.5:7b", 5.0, 6.0, 4.7, 7, "Good quality — needs ~6 GB VRAM or ~10 GB RAM"),
    ModelSpec("llama3.1:8b", 6.0, 7.0, 4.9, 7, "Alternative to qwen2.5:7b"),
    ModelSpec("gemma2:9b", 7.0, 8.0, 5.4, 8, "High quality — needs ~12 GB RAM"),
    ModelSpec("qwen2.5:14b", 9.0, 10.0, 9.0, 9, "Very high quality — needs ~16 GB VRAM"),
    ModelSpec("llama3.3:70b", 42.0, 45.0, 43.0, 10, "Excellent — high-end GPU or 64 GB+ RAM"),
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


def band_for(quality: int | None) -> tuple[str, str]:
    """Map the best fitting model's quality rank to ``(band, summary)``."""
    if quality is None:
        return NO_FIT_BAND, NO_FIT_SUMMARY
    for threshold, name, summary in _BANDS:
        if quality >= threshold:
            return name, summary
    return NO_FIT_BAND, NO_FIT_SUMMARY
