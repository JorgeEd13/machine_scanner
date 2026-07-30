"""Data model for a machine inventory.

Everything a collector produces is a `Section`; the whole scan is an
`Inventory` (metadata + ordered sections). Keeping the shape this uniform is
deliberate: the report renderers (JSON / text / HTML) never need to know about
individual collectors — they walk `Inventory.sections` generically. Adding a
new collector therefore needs zero changes in the reporting layer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Status(str, Enum):
    """Outcome of a single collector.

    Inherits from `str` so it serializes to a plain string in JSON without a
    custom encoder.
    """

    OK = "ok"                    # collected everything it set out to
    PARTIAL = "partial"          # some fields collected, some missing
    UNAVAILABLE = "unavailable"  # nothing to collect here (e.g. no GPU)
    UNSUPPORTED = "unsupported"  # not implemented for this OS yet
    ERROR = "error"              # the collector raised — see notes


@dataclass
class Section:
    """One topic of the inventory (cpu, memory, disk, network, ...)."""

    name: str                                   # machine key, e.g. "cpu"
    title: str                                  # human label, e.g. "CPU"
    status: Status = Status.OK
    data: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)  # warnings / caveats

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "title": self.title,
            "status": self.status.value,
            "data": self.data,
            "notes": self.notes,
        }


@dataclass
class Inventory:
    """A full scan: run metadata plus the ordered sections."""

    meta: dict[str, Any] = field(default_factory=dict)
    sections: list[Section] = field(default_factory=list)

    def section(self, name: str) -> Section | None:
        return next((s for s in self.sections if s.name == name), None)

    def to_dict(self) -> dict[str, Any]:
        return {
            "meta": self.meta,
            "sections": [s.to_dict() for s in self.sections],
        }
