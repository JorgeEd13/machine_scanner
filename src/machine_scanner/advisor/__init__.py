"""Advisor — derived analysis over a completed scan.

A **collector** probes the machine. An **advisor** probes nothing: it reads an
already-collected :class:`~machine_scanner.core.models.Inventory` and derives an
answer from it. That separation is why this is not a collector — a collector is
a zero-arg callable that cannot see its siblings, and "which local LLM fits this
box" is a question about the CPU, memory, GPU *and* disk sections at once.

Deriving instead of re-probing also means the advisor is **pure**: same scan in,
same verdict out, no subprocess, no hardware assumptions in its tests. See
ADR-019.
"""

from .catalog import CATALOG, ModelSpec
from .fit import ADVISOR_NAME, append_to, build_section, extract_profile, recommend
from .summary import to_summary

__all__ = [
    "ADVISOR_NAME",
    "CATALOG",
    "ModelSpec",
    "append_to",
    "build_section",
    "extract_profile",
    "recommend",
    "to_summary",
]
